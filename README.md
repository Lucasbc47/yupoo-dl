# yupoo_dl

CLI para baixar imagens de álbuns do [Yupoo](https://yupoo.com).

## Instalação

```bash
pip install -r requirements.txt
```

## Uso

**Modo interativo** (recomendado):

```bash
python yupoo_dl.py
```

O script vai pedir o URL, tamanho e pasta de destino.

**Linha de comando:**

```bash
python yupoo_dl.py <url>
python yupoo_dl.py <url> --size large
python yupoo_dl.py <url> --size medium --output C:/fotos
```

> No Windows CMD, coloque o URL entre aspas para evitar que o `&` seja interpretado como separador de comandos:
>
> ```bash
> python yupoo_dl.py "https://loja.x.yupoo.com/albums/123456?uid=1&isSubCate=false"
> ```

### Opções

| Argumento         | Descrição                                       | Padrão        |
| ----------------- | ----------------------------------------------- | ------------- |
| `url`             | URL do álbum Yupoo                              | —             |
| `--size` / `-s`   | Tamanho das imagens: `small`, `medium`, `large` | `medium`      |
| `--output` / `-o` | Pasta de destino                                | `./downloads` |

## Estrutura de saída

```
downloads/
└── Nome do Álbum/
    ├── e4b0ca82.jpg
    ├── 076948b2.jpg
    └── ...
```

## Dependências

- `aiohttp` — requisições HTTP assíncronas
- `aiofiles` — escrita de arquivo assíncrona
- `beautifulsoup4` + `lxml` — parsing do HTML
- `rich` — interface no terminal
- `alive-progress` — barra de progresso
- `certifi` — certificados SSL

## Notas

- Imagens já baixadas são puladas automaticamente.
- Erros são registrados em `yupoo_dl.log`.
- Não utiliza cookies do navegador — apenas cookies de sessão anônimos definidos pelo próprio Yupoo durante a requisição.
  echo dist/ >> .gitignore