"""Where menus come from.

siksha.py serves the daily SNU cafeteria menus. The official SNU co-op page
(https://snuco.snu.ac.kr/foodmenu/?date=YYYY-MM-DD) is the planned fallback and
would live next to it, returning the same MenuRecord list.

naver_stores.py reads the crawl of the restaurants near 서울대입구역 and 낙성대역
(general menu mode); it is imported whenever the stores are crawled again.
"""
