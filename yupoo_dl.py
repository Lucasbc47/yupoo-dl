#!/usr/bin/env python3
"""
Yupoo Album Downloader - CLI
Usage:
  python yupoo_dl.py
  python yupoo_dl.py <url>
  python yupoo_dl.py <url> --size large --output ./fotos
"""

import os
import re
import sys
import asyncio
import logging
import argparse

from pathlib import Path
from time import perf_counter

import aiohttp
import aiofiles

from bs4 import BeautifulSoup
from rich.console import Console
from rich.prompt import Prompt
from alive_progress import alive_bar

import ssl
import certifi

sslcontext = ssl.create_default_context(cafile=certifi.where())

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%d/%m/%Y %H:%M:%S',
    handlers=[logging.FileHandler('yupoo_dl.log', encoding='utf-8')]
)
logger = logging.getLogger(__name__)

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'referer': 'https://yupoo.com/'
}

console = Console(color_system="auto")

SIZE_OPTIONS = ['small', 'medium', 'large']


def normalize_url(url: str) -> str:
    url = url.strip().rstrip('/')
    if '?' in url:
        base = url.split('?')[0]
        return f"{base}?uid=1"
    return f"{url}?uid=1"


def replace_size(url: str, size: str) -> str:
    return re.sub(r'/(small|medium|large)(\.(jpg|jpeg|png|webp))', f'/{size}\\2', url)


def safe_filename(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip()


class YupooDownloader:
    def __init__(self, url: str, size: str, output: str):
        self.url = normalize_url(url)
        self.size = size
        self.output = output
        self.sem = asyncio.Semaphore(30)
        self.timeout = aiohttp.ClientTimeout(connect=30, sock_read=30)
        self.failed: list[str] = []

    async def _get(self, session: aiohttp.ClientSession, url: str) -> str:
        for attempt in range(6):
            try:
                async with session.get(url, headers=HEADERS, ssl=sslcontext, timeout=self.timeout) as r:
                    if r.status == 200:
                        return await r.text()
                    logger.warning(f"HTTP {r.status} — {url}")
            except Exception as e:
                logger.warning(f"[attempt {attempt+1}] {url}: {e}")
                await asyncio.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"Falha ao buscar: {url}")

    async def _get_bytes(self, session: aiohttp.ClientSession, url: str) -> bytes | None:
        headers = {**HEADERS, 'referer': self.url.split('?')[0]}
        for attempt in range(6):
            try:
                async with session.get(url, headers=headers, ssl=sslcontext, timeout=self.timeout) as r:
                    if r.status == 200:
                        return await r.read()
                    logger.warning(f"HTTP {r.status} — {url}")
                    if r.status in (403, 404, 567):
                        return None
            except Exception as e:
                logger.warning(f"[attempt {attempt+1}] {url}: {e}")
                await asyncio.sleep(1.5 * (attempt + 1))
        return None

    async def _get_pages(self, session: aiohttp.ClientSession, url: str) -> list[str]:
        html = await self._get(session, url)
        soup = BeautifulSoup(html.encode('ascii', 'ignore').decode('utf-8'), 'lxml')
        try:
            total = int(soup.select_one('form.pagination__jumpwrap input[name="page"]').get('max'))
        except Exception:
            total = 1

        base = re.sub(r'[&?]page=\d+', '', url)
        sep = '&' if '?' in base else '?'
        return [f"{base}{sep}page={p}" for p in range(1, total + 1)]

    async def _get_images_from_page(self, session: aiohttp.ClientSession, page_url: str) -> tuple[str, list[str]]:
        html = await self._get(session, page_url)
        soup = BeautifulSoup(html.encode('ascii', 'ignore').decode('utf-8'), 'lxml')

        title_el = soup.select_one('span.showalbumheader__gallerytitle')
        title = safe_filename(title_el.text.strip()) if title_el else 'album'

        imgs: list[str] = []
        for div in soup.find_all('div', {'class': 'showalbum__children'}):
            wrap = div.select_one('.image__imagewrap')
            if wrap and wrap.get('data-type') == 'video':
                continue
            img_tag = div.find('img')
            if not img_tag:
                continue
            src = img_tag.get('data-origin-src', '')
            if not src:
                continue
            base = '/'.join(src.split('/')[:-1])
            prefix = 'https:' if src.startswith('//') else ''
            imgs.append(f"{prefix}{base}/{self.size}.jpg")
        return title, imgs

    async def _download_one(self, session: aiohttp.ClientSession, url: str, path: str, bar) -> None:
        async with self.sem:
            data = await self._get_bytes(session, url)
            if data:
                async with aiofiles.open(path, 'wb') as f:
                    await f.write(data)
            else:
                self.failed.append(url)
                logger.error(f"Download falhou: {url}")
            bar()

    async def run(self) -> None:
        t0 = perf_counter()

        # unsafe=True allows cookies to flow across subdomains (e.g. yupoo.com → photo.yupoo.com)
        jar = aiohttp.CookieJar(unsafe=True)
        async with aiohttp.ClientSession(cookie_jar=jar) as session:
            console.print(f"\n[#6149ab]Álbum:[/] {self.url}")

            # Paginas do album
            try:
                pages = await self._get_pages(session, self.url)
            except Exception as e:
                console.print(f"[red]Erro ao buscar álbum: {e}[/]")
                return

            # Coletar todas as imagens
            all_imgs: list[str] = []
            album_title = 'album'
            for page_url in pages:
                try:
                    title, imgs = await self._get_images_from_page(session, page_url)
                    album_title = title
                    all_imgs.extend(imgs)
                except Exception as e:
                    logger.error(f"Erro na página {page_url}: {e}")

            if not all_imgs:
                console.print("[red]Nenhuma imagem encontrada.[/]")
                return

            # Criar pasta
            save_dir = Path(self.output) / album_title
            save_dir.mkdir(parents=True, exist_ok=True)

            console.print(f"[#6149ab]Título:[/]  [bold]{album_title}[/]")
            console.print(f"[#6149ab]Imagens:[/] {len(all_imgs)} ({self.size})")
            console.print(f"[#6149ab]Pasta:[/]   {save_dir.resolve()}\n")

            # Montar fila de download (pular já existentes)
            queue: list[tuple[str, str]] = []
            for img_url in all_imgs:
                # URL: https://photo.yupoo.com/user/IMAGE_ID/medium.jpg
                # Use IMAGE_ID (second-to-last segment) as unique filename
                parts = img_url.rstrip('/').split('/')
                img_id = parts[-2] if len(parts) >= 2 else re.sub(r'\W', '_', img_url[-16:])
                fname = f"{img_id}.jpg"
                path = str(save_dir / fname)
                if not os.path.exists(path):
                    queue.append((img_url, path))

            skipped = len(all_imgs) - len(queue)
            if skipped:
                console.print(f"[#baa6ff]{skipped} imagens já existentes, pulando.[/]")

            if not queue:
                console.print("[#0ba162]Tudo já foi baixado![/]")
                return

            console.print(f"[#6149ab]Baixando {len(queue)} imagens...[/]")
            with alive_bar(len(queue), length=35, bar='squares', spinner='classic', elapsed='em {elapsed}') as bar:
                tasks = [
                    asyncio.ensure_future(self._download_one(session, url, path, bar))
                    for url, path in queue
                ]
                await asyncio.gather(*tasks)

        elapsed = round(perf_counter() - t0, 2)
        ok = len(queue) - len(self.failed)
        console.print(f"\n[bold #0ba162]Concluído![/] {ok}/{len(queue)} imagens em {elapsed}s")
        if self.failed:
            console.print(f"[red]{len(self.failed)} falharam — veja yupoo_dl.log[/]")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='yupoo_dl',
        description='Baixa imagens de álbuns do Yupoo',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""exemplos:
  python yupoo_dl.py
  python yupoo_dl.py https://loja.x.yupoo.com/albums/123456
  python yupoo_dl.py https://loja.x.yupoo.com/albums/123456 --size large
  python yupoo_dl.py https://loja.x.yupoo.com/albums/123456 --size medium -o C:/fotos
"""
    )
    p.add_argument('url', nargs='?', help='URL do álbum Yupoo')
    p.add_argument(
        '--size', '-s',
        choices=SIZE_OPTIONS,
        default=None,
        metavar='SIZE',
        help='Tamanho das imagens: small | medium | large  (padrão: medium)'
    )
    p.add_argument(
        '--output', '-o',
        default=None,
        help='Pasta de destino  (padrão: ./downloads)'
    )
    return p


def main() -> None:
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    console.print("\n[bold #4912ff]Yupoo Downloader[/] [#baa6ff]v1.0 — CLI[/]\n")

    args = build_parser().parse_args()

    url: str = args.url or Prompt.ask("[#6149ab b]URL do álbum[/]").strip()
    size: str = args.size or Prompt.ask(
        "[#6149ab b]Tamanho[/]",
        choices=SIZE_OPTIONS,
        default='medium'
    )
    output: str = args.output or Prompt.ask(
        "[#6149ab b]Pasta de destino[/]",
        default='./downloads'
    ).strip()

    if 'yupoo' not in url:
        console.print("[red]URL inválida — use um link do Yupoo.[/]")
        sys.exit(1)

    asyncio.run(YupooDownloader(url=url, size=size, output=output).run())


if __name__ == '__main__':
    main()
