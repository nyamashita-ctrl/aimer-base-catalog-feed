#!/usr/bin/env python3
"""Build a Meta Commerce product feed (CSV) from the public pages of a BASE shop.

Reads only public pages (top page, category pages, product pages) with a polite
delay, so it needs no BASE credentials and no BASE API.
Product `id` = BASE item ID, which is what the BASE pixel sends as content_ids,
so Advantage+ catalog ads can match browsing events to catalog items.
"""
import csv
import html as htmlmod
import re
import sys
import time
import urllib.request

SHOP = "https://aimer12.base.shop"
BRAND_FALLBACK = "Aimer"
DELAY_SEC = 1.2
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36 aimer-catalog-feed/1.0")

FIELDS = ["id", "title", "description", "availability", "condition", "price",
          "link", "image_link", "additional_image_link", "brand", "product_type",
          "custom_label_0"]


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8", "replace")
    time.sleep(DELAY_SEC)
    return body


def strip_tags(s):
    s = re.sub(r"<br\s*/?>", " ", s, flags=re.I)
    s = re.sub(r"</p>", " ", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = htmlmod.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def meta(h, prop):
    m = re.search(r'<meta (?:property|name)="%s" content="([^"]*)"' % re.escape(prop), h)
    return htmlmod.unescape(m.group(1)) if m else ""


def item_ids(h):
    seen, out = set(), []
    for m in re.finditer(r'href="%s/items/(\d+)"' % re.escape(SHOP), h):
        if m.group(1) not in seen:
            seen.add(m.group(1))
            out.append(m.group(1))
    return out


def category_tree(h):
    """[(parent_name, child_name, url)] from the header navigation."""
    out = []
    nav = re.search(r'<ul id="appsItemCategoryTag">(.*?)</ul>\s*</nav>', h, re.S)
    if not nav:
        return out
    for parent in re.finditer(
            r'<li class="appsItemCategoryTag_child">\s*<a href="([^"]+)"[^>]*>(.*?)</a>(.*?)(?=<li class="appsItemCategoryTag_child">|$)',
            nav.group(1), re.S):
        purl, pname, rest = parent.group(1), strip_tags(parent.group(2)), parent.group(3)
        children = re.findall(r'<a href="([^"]+)"[^>]*appsItemCategoryTag_lowerLink[^>]*>(.*?)</a>', rest, re.S)
        if children:
            for curl, cname in children:
                out.append((pname, strip_tags(cname), curl))
        else:
            out.append((pname, "", purl))
    return out


def parse_item(h, item_id):
    title = ""
    m = re.search(r'<h1 class="item-detail__ttl">(.*?)</h1>', h, re.S)
    if m:
        title = strip_tags(m.group(1))
    if not title:
        title = meta(h, "og:title").split(" | ")[0].strip()

    desc = ""
    m = re.search(r'<div class="item-detail__desc">(.*?)</div>', h, re.S)
    if m:
        desc = strip_tags(m.group(1))
    if not desc:
        desc = meta(h, "description") or meta(h, "og:description")
    if not desc:
        desc = title
    desc = desc[:4900]

    amount = meta(h, "product:price:amount")
    currency = meta(h, "product:price:currency") or "JPY"
    if not amount:
        m = re.search(r"'itemPrice':\s*(\d+)", h)
        amount = m.group(1) if m else ""
    price = f"{amount} {currency}" if amount else ""

    # availability
    availability = "out of stock"
    form = re.search(r'<form id="purchase_form".*?</form>', h, re.S)
    if form:
        f = form.group(0)
        stocks = re.findall(r'<option[^>]*data-stock="(\d+)"', f)
        if stocks:
            availability = "in stock" if any(int(s) > 0 for s in stocks) else "out of stock"
        else:
            btn = re.search(r'<div class="purchaseButton">(.*?)</div>', f, re.S)
            seg = btn.group(1) if btn else f
            if "purchaseButton__btn--outOfStock" in seg and "purchaseButton__btn--addToCart" not in seg:
                availability = "out of stock"
            elif "purchaseButton__btn--addToCart" in seg:
                availability = "in stock"

    image = meta(h, "og:image")
    imgs = []
    slider = re.search(r'<ul class="item-detail__mainSlider__list.*?</ul>', h, re.S)
    if slider:
        for u in re.findall(r'(https://baseec-img-mng\.akamaized\.net/images/item/origin/[^"?\s]+)', slider.group(0)):
            u = u + "?imformat=generic&q=90&im=Resize,width=1200,type=normal"
            if u not in imgs:
                imgs.append(u)
    if not image and imgs:
        image = imgs[0]
    additional = [u for u in imgs if u.split("?")[0] != image.split("?")[0]][:10]

    members_only = bool(re.search(r'item-detail__tag[^>]*community[^>]*>\s*会員限定商品', h))

    return {
        "id": item_id,
        "title": title,
        "description": desc,
        "availability": availability,
        "condition": "new",
        "price": price,
        "link": f"{SHOP}/items/{item_id}",
        "image_link": image,
        "additional_image_link": ",".join(additional),
        "brand": BRAND_FALLBACK,
        "product_type": "",
        "custom_label_0": "members_only" if members_only else "",
    }


def main(out_path):
    top = fetch(SHOP + "/")
    ids = item_ids(top)
    print(f"items on top page: {len(ids)}", file=sys.stderr)

    # item -> category path (first hit wins; parent name doubles as brand)
    cat_of = {}
    for pname, cname, curl in category_tree(top):
        try:
            ch = fetch(curl)
        except Exception as e:  # keep going; category is optional metadata
            print(f"category fetch failed {curl}: {e}", file=sys.stderr)
            continue
        for iid in item_ids(ch):
            if iid not in ids:
                ids.append(iid)
            cat_of.setdefault(iid, (pname, cname))
    print(f"items incl. categories: {len(ids)}", file=sys.stderr)

    rows = []
    for iid in ids:
        try:
            h = fetch(f"{SHOP}/items/{iid}")
        except Exception as e:
            print(f"item fetch failed {iid}: {e}", file=sys.stderr)
            continue
        row = parse_item(h, iid)
        if iid in cat_of:
            pname, cname = cat_of[iid]
            row["product_type"] = f"{pname} > {cname}" if cname else pname
            row["brand"] = pname or BRAND_FALLBACK
        if not (row["title"] and row["price"] and row["image_link"]):
            print(f"skip {iid}: missing title/price/image", file=sys.stderr)
            continue
        rows.append(row)

    if len(rows) < max(1, int(len(ids) * 0.8)):
        print(f"too few rows ({len(rows)}/{len(ids)}); refusing to write feed", file=sys.stderr)
        sys.exit(2)

    with open(out_path, "w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=FIELDS, quoting=csv.QUOTE_ALL, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"wrote {len(rows)} rows to {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "feed.csv")
