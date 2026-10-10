from core.textutils import answers_match, fa_num, normalize_fa, parse_int


def test_arabic_letters_are_unified():
    assert normalize_fa("كتاب علي") == "کتاب علی"


def test_diacritics_and_kashida_removed():
    assert normalize_fa("مُحَمَّد") == "محمد"
    assert normalize_fa("ســـلام") == "سلام"


def test_half_space_becomes_space_or_removed():
    assert normalize_fa("می‌روم") == "می روم"
    assert normalize_fa("می‌روم", keep_spaces=False) == "میروم"


def test_digits_converted_to_english():
    assert normalize_fa("۱۲۳ ٤٥٦") == "123 456"


def test_trim_and_collapse_spaces():
    assert normalize_fa("  سلام   دنیا \n") == "سلام دنیا"


def test_answers_match_ignores_spacing_variants():
    assert answers_match("كتاب‌خانه", "کتابخانه")
    assert answers_match(" کتاب خانه ", "کتاب‌خانه")
    assert not answers_match("کتاب", "کتابخانه")


def test_fa_num_grouping():
    assert fa_num(12500) == "۱۲٬۵۰۰"
    assert fa_num(0) == "۰"


def test_parse_int():
    assert parse_int("۴۲") == 42
    assert parse_int(" ١٢٣ ") == 123
    assert parse_int("-7") == -7
    assert parse_int("12a") is None
    assert parse_int("") is None
