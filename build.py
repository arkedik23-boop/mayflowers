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

if __name__ == "__main__":
    if "--demo" in sys.argv:
        sys.stdout.write(build(demo=True))
    else:
        (ROOT / "index.html").write_text(build(), encoding="utf-8")
        print("index.html собран")
