# Store audit and roadmap

This document answers the audit tasks and records exactly what was implemented
versus what still needs live evidence from your machine. The guiding rule was
yours: no speculative spiders, only verified extraction paths.

## Task 1 — Store audit (prioritized)

Status reflects live results where we have them and a labelled assessment
otherwise. Difficulty is the effort to a reliable, maintained spider.

| Priority | Store | Status | Technology | Preferred method | Difficulty |
|---|---|---|---|---|---|
| Working now | wayupsports | Working (9,239) | Shopify | JSON endpoint | Easy |
| Working now | townteam | Working (2,968) | Shopify | JSON endpoint | Easy |
| Working now | intersport | Working (2,514) | Shopify | JSON endpoint | Easy |
| Working now | iravin | Working (1,810) | Shopify | JSON endpoint | Easy |
| Working now | lablanca | Working (430) | Shopify | JSON endpoint | Easy |
| Working now | gorillaoutfit | Working (313) | Shopify | JSON endpoint | Easy |
| Working now | sigmafit | Working (210) | Shopify | JSON endpoint | Easy |
| Working now | basiclook | Working earlier (75), 0 last run | Shopify | JSON endpoint | Easy |
| Ready to run | carinawear, tomatostore, magmasportswear, pinkshop, tiehouse, youremma, izzyapparel, mobaco, lavitoscarf, andora | Untested live (registered) | Shopify (likely) | JSON endpoint | Easy |
| Ready to run | americaneagle, accessorize, aloyoga | Untested live (registered) | Shopify (verify) | JSON endpoint | Easy to Medium |
| Working now | decathlon | Working (JSON LD ProductGroup, verified from evidence) | Custom (PrestaShop) | JSON LD | Medium |
| Needs evidence | lcwaikiki | Untested live | Custom | JSON LD | Medium |
| Blocked | defacto | Blocked (403) | Custom / Next.js | JSON LD then HTML | Hard |
| Needs evidence | mitcha | Unsupported | Custom (not Shopify) | unknown until inspected | Hard |
| Needs evidence | jumia | Unsupported | Custom marketplace | JSON LD or API | Hard |
| Needs evidence | noon | Unsupported | Custom marketplace | mobile or REST API | Hard |
| Needs evidence | decathlon | Unsupported | Custom | REST API | Medium to Hard |
| Needs evidence | mango | Unsupported | Custom | embedded JSON | Hard |
| Needs evidence | maxfashion | Unsupported | Custom | REST API | Hard |
| Anti bot | adidas, newbalance, lacoste | Unsupported | Salesforce Commerce | embedded JSON or API | Hard |
| Anti bot | zara, pullandbear | Unsupported | Inditex custom | REST API | Hard |
| Anti bot | hm | Unsupported | Custom | REST API | Hard |
| Anti bot | nike | Unsupported | Custom | REST API | Very Hard |
| Anti bot | amazon | Unsupported | Amazon | mobile API | Very Hard |
| Needs evidence | dabchy | Unsupported | Custom marketplace | API or HTML | Hard |

## Task 2 — Highest ROI implementations (done)

The highest return work is not new spiders, it is finishing the platform we
already support well. Concretely:

* The eight confirmed Shopify stores work and yield about 17,500 products.
* Thirteen more likely Shopify stores are registered and runnable now with
  zero new code (`python -m egyscraper.run --candidates`). Each is one
  `/products.json` check away from confirmed.
* The Shopify spider now self heals: if the store wide endpoint is empty,
  blocked, or missing, it falls back to collection discovery automatically.
* The generic JSON LD spider covers structured custom stores with only a
  sitemap and a product url pattern, no per store parsing code.

No speculative spiders were added. Browser automation was avoided entirely.

## Task 3 — DeFacto analysis and anti bot work (done, with honest limits)

What happened: DeFacto returned 403 on both robots.txt and sitemap.xml. A 403
on robots.txt from a normal request is the signature of an IP plus fingerprint
bot manager (Akamai or DataDome class), not a simple user agent check.

Improvements implemented, all without paid services:

* Browser like default headers (Accept, Accept-Language with Arabic, Sec-Fetch
  set, Upgrade-Insecure-Requests), applied to every request.
* Coherent browser profile rotation: each request now carries a user agent
  together with the matching sec-ch-ua client hint headers, so the fingerprint
  is internally consistent rather than an obvious bot signature.
* Cookie and session handling: Scrapy's cookie middleware is on, so a session
  cookie handed out on the first response is carried on later requests.
* Sitemap discovery fallback: the JSON LD spider reads robots.txt for Sitemap
  directives and, if the primary sitemap fails, tries common locations
  (sitemap_index.xml and similar) once.
* Retry strategy: transient codes (429, 5xx, timeouts) retry with backoff via
  AutoThrottle; a hard 403 is not retried blindly, since that only hammers a
  WAF without changing the outcome.

Expected impact: these defeat naive bot rules and will unblock stores whose
protection is light. They are unlikely to beat DeFacto specifically, because a
403 on robots.txt points to IP or TLS fingerprint blocking that headers cannot
change from a datacenter IP. The honest next steps for DeFacto, in order, are a
residential proxy (the ProxyMiddleware hook is ready, set PROXY_URL or
PROXY_LIST) and, only if that fails, Playwright with a real browser fingerprint
(the settings have the handlers commented and ready). To confirm which is
needed, see the evidence request in Task 7.

## Task 4 — Mitcha investigation (no speculative code)

Finding: Mitcha is not Shopify. Both `/products.json` and `/collections.json`
return HTML with status 200, which means the Shopify JSON endpoints do not
exist; the server returns the application shell instead. Mitcha has been
removed from the confirmed Shopify list and the fallback now gives up cleanly.

Likely platform: a custom or Next.js style single page storefront or
marketplace, where product data is either embedded in the page as a hydration
payload or fetched from an internal API by the browser after load.

Likely extraction strategy, to be confirmed by inspection: either parse the
embedded payload (a `__NEXT_DATA__` script tag or a Product JSON LD block) from
a product page, or call the internal product API directly once its url is
known.

No spider was written, because the correct path cannot be chosen without seeing
a real product page. The exact evidence needed is in Task 7.

## Task 5 — BasicLook analysis and fix (done)

BasicLook is a confirmed Shopify store that returned 75 products in the first
full run and 0 in a later run. Endpoint, parser and filtering are therefore not
the cause (they worked days earlier on the same store). The most likely causes
are a transient block during the back to back `--candidates` batch (many stores
crawled in sequence can trip a rate limit), compounded by an export weakness:
the old exporter opened the output file in truncate mode, so a later zero
result overwrote the earlier good file.

Fix implemented: the exporter now writes to a temp file and swaps atomically on
success, and it refuses to overwrite a previous non empty file with a zero
result, logging a warning instead. A blocked or interrupted run can no longer
destroy good data. To re check BasicLook on its own:

```
scrapy crawl shopify -a store=basiclook
```

If it returns products, the earlier zero was transient and your data is now
safe from being clobbered. If it returns zero with a non JSON warning, the
store is temporarily blocking; wait and retry, or apply the proxy step.

## Task 6 — Validation framework (done)

Every crawl now emits a health report. On spider close the framework logs a one
line summary and writes `data/<store>/crawl_report.json` with products scraped,
requests made, retries, failures, dropped items, duration, and products per
request. A CLI aggregates all stores into one yield table:

```
python -m egyscraper.report
```

This automates the per store summaries and gives an objective signal for
judging any future spider: a healthy crawl has a sensible products per request
ratio and few failures; a blocked one shows zero products with failures.

## Task 7 — Remaining stores roadmap (explicit)

Group A, can proceed now, no new evidence. Run these and confirm with the
report CLI. If any return zero with a non JSON warning, treat as Group D.
* carinawear, tomatostore, magmasportswear, pinkshop, tiehouse, youremma,
  izzyapparel, mobaco, lavitoscarf, andora, americaneagle, accessorize, aloyoga.
* Command: `python -m egyscraper.run --candidates`, then `python -m egyscraper.report`.

Group B, structured custom stores, need one live check each (no blocking
expected). For each, open one product page and confirm it contains a schema.org
Product JSON LD block, then give me the product url pattern.
* lcwaikiki: registered as a JSON LD candidate; confirm sitemap and that
  product pages carry Product JSON LD.
* Evidence to send: one product page url, and the saved HTML of that page
  (View Source, save as .html). I will confirm the JSON LD path and finalize
  the store config.

Group C, custom stores needing inspection to choose the path (Mitcha, Jumia,
Noon, Decathlon, Mango, MaxFashion, Dabchy). Implementation cannot start until
the extraction path is known. For each, send:
* The product page url and its saved HTML (View Source).
* In the browser DevTools Network tab, filter to Fetch or XHR, reload the
  product or a category page, and save (right click, Save all as HAR, or copy
  the response) the JSON request that returns the product data. The request url
  and one JSON response body is enough.
* For Mitcha specifically: check the page source for a `__NEXT_DATA__` script or
  a Product JSON LD block, and capture any XHR call to an api or graphql path.

With one product page plus one product API response per store, I can build and
unit test a real spider against that captured sample, the same way the Shopify
and JSON LD spiders were verified.

Group D, anti bot protected (DeFacto, Adidas, New Balance, Lacoste, Zara, Pull
and Bear, H and M, Nike, Amazon). These need an access method before any spider
matters. Decide per store in this order:
* Try the implemented header and profile work first: run it and capture the log.
* If it 403s, the evidence I need is the response status and headers for
  robots.txt and one product url (the DevTools response headers, or curl with
  `-i`), so I can identify the WAF and tell you whether a residential proxy is
  enough or Playwright is required.
* These are deliberately last; they carry the highest maintenance cost and the
  lowest certainty, and the catalog already has real scale without them.

Summary of what is needed from you to finish the rest: run Group A and paste the
report table; for Group B and C send one product page HTML and one product API
response per store; for Group D send the 403 response headers. Each piece lets
me build a verified spider rather than a guess.

## Project scope change (clothing + footwear only)

Following live crawl validation a scope filter was added. Accessories, sports
equipment, electronics, and home goods are now rejected before export.

**Estimated impact on the current ~33k product corpus:**
- wayupsports, townteam, intersport, iravin, lablanca, gorillaoutfit, sigmafit,
  basiclook: pure clothing or sportswear Shopify stores. Estimated retention
  80-95%. Accessories (belts, bags) and equipment in mixed catalogs will be
  dropped.
- decathlon: general sporting goods retailer; apparel and footwear are a
  minority. Estimated retention 20-35%.
- Run `python -m egyscraper.scope_audit data/` for exact numbers on your
  machine once the data directory is populated.

The scope classification is fully deterministic; re-running the audit script
after a crawl gives exact before/after counts.
