"""Curated list of popular world-level badminton players.

Used to offer quick-pick suggestions in the interactive scraper. Ordered
roughly by contemporary popularity / world ranking relevance across the
men's singles, women's singles and doubles disciplines.
"""

from __future__ import annotations

# (Name, discipline / short note) pairs kept together so the UI can show a hint.
POPULAR_PLAYERS: list[tuple[str, str]] = [
    # Men's singles
    ("Viktor Axelsen", "MS · Denmark"),
    ("Kento Momota", "MS · Japan"),
    ("Lin Dan", "MS · China"),
    ("Lee Chong Wei", "MS · Malaysia"),
    ("Chen Long", "MS · China"),
    ("Shi Yuqi", "MS · China"),
    ("Anthony Sinisuka Ginting", "MS · Indonesia"),
    ("Jonatan Christie", "MS · Indonesia"),
    ("Kunlavut Vitidsarn", "MS · Thailand"),
    ("Loh Kean Yew", "MS · Singapore"),
    ("Lakshya Sen", "MS · India"),
    ("Anders Antonsen", "MS · Denmark"),
    ("Lee Zii Jia", "MS · Malaysia"),
    ("Chou Tien-chen", "MS · Chinese Taipei"),
    # Women's singles
    ("An Se-young", "WS · Korea"),
    ("Tai Tzu-ying", "WS · Chinese Taipei"),
    ("Carolina Marin", "WS · Spain"),
    ("Chen Yufei", "WS · China"),
    ("Akane Yamaguchi", "WS · Japan"),
    ("P. V. Sindhu", "WS · India"),
    ("Ratchanok Intanon", "WS · Thailand"),
    ("Nozomi Okuhara", "WS · Japan"),
    ("He Bingjiao", "WS · China"),
    ("Wang Zhiyi", "WS · China"),
    ("Gregoria Mariska Tunjung", "WS · Indonesia"),
    ("Pornpawee Chochuwong", "WS · Thailand"),
    # Doubles legends / stars
    ("Kevin Sanjaya Sukamuljo", "MD · Indonesia"),
    ("Marcus Fernaldi Gideon", "MD · Indonesia"),
    ("Mohammad Ahsan", "MD · Indonesia"),
    ("Hendra Setiawan", "MD · Indonesia"),
    ("Lee Yang", "MD · Chinese Taipei"),
    ("Wang Chi-lin", "MD · Chinese Taipei"),
    ("Fajar Alfian", "MD · Indonesia"),
    ("Muhammad Rian Ardianto", "MD · Indonesia"),
    ("Takuro Hoki", "MD · Japan"),
    ("Liang Weikeng", "MD · China"),
    ("Chen Qingchen", "WD/XD · China"),
    ("Jia Yifan", "WD · China"),
    ("Zheng Siwei", "XD · China"),
    ("Huang Yaqiong", "XD · China"),
    ("Dechapol Puavaranukroh", "XD · Thailand"),
]
