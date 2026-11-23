"""Собирает index.html из src/. Запуск: python build.py
Демо-версия без отправки заказов: python build.py --demo > demo.html"""
import sys, pathlib
ROOT = pathlib.Path(__file__).parent
SRC = ROOT / "src"
# Адрес бота и ключ приёма заказов. Ключ всё равно виден в коде страницы (см. bot/README.md).
ORDER_URL = "https://mayflowers.185-192-246-4.sslip.io"
INTAKE_KEY = "wEuYTuPr5th8H2zSylcdihwUjdkPX5FZ"

def build(demo=False):
    r = lambda n: (SRC / n).read_text(encoding="utf-8")
    js = r("1-data.js") + r("2-shop.js") + r("3-app.js")
    stub = "const ORDER_API={url:'',key:''};"
    assert stub in js, "в 1-data.js нет строки ORDER_API"
    if not demo:
        js = js.replace(stub, "const ORDER_API={url:'%s',key:'%s'};" % (ORDER_URL, INTAKE_KEY))
    return (r("head.html") + r("styles.html") + "\n</head><body>\n" + r("body.html")
            + "\n<script>\n" + js + "\n</script>\n</body></html>\n")

CARD_SKELETON = ('<!doctype html><html lang="ru"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
    '<style>:root{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}'
    'body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>')

def build_card(demo=False):
    """card.html: страница аудио/видео-открытки по QR-коду (card.html?c=ТОКЕН)."""
    src = (SRC / "card.html").read_text(encoding="utf-8")
    head, body = src.split("<!--body-->", 1)
    if not demo:
        assert "const API='';" in body
        body = body.replace("const API='';", "const API='%s';" % ORDER_URL)
    return CARD_SKELETON + head + "</head><body>" + body + "</body></html>\n"

if __name__ == "__main__":
    if "--demo" in sys.argv:
        sys.stdout.write(build(demo=True))
    else:
        (ROOT / "index.html").write_text(build(), encoding="utf-8")
        (ROOT / "card.html").write_text(build_card(), encoding="utf-8")
        print("index.html и card.html собраны")
