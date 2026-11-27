"""Language guard, both directions: diagnoses are blocked; counts of the user's own data
and (opt-in) clearly attributed doctor statements are allowed."""

import pytest

from app.services.language_guard import is_diagnostic


@pytest.mark.parametrize(
    "text",
    [
        "You have hypertension.",
        "You probably have diabetes.",
        "you may have a thyroid disorder",
        "You have type 2 diabetes",
        "You might have an infection.",
        "You have migraines.",
        "This is caused by stress.",
        "You should take ibuprofen.",
        "Dr. Rao diagnosed type 2 diabetes in 2018.",  # not exempt unless the caller opts in
    ],
)
def test_diagnostic_text_is_blocked(text):
    assert is_diagnostic(text)


@pytest.mark.parametrize(
    "text",
    [
        "You have logged 3 headaches this month.",
        "You have had 3 migraines since May.",
        "You have recorded your blood pressure 4 times this week.",
        "You have been logging regularly.",
        "Do you have any other symptoms today?",
        "Headache episodes increased to 3 in two months.",
    ],
)
def test_counts_of_the_users_own_data_are_allowed(text):
    assert not is_diagnostic(text)


@pytest.mark.parametrize(
    "text",
    [
        "Dr. Rao diagnosed type 2 diabetes in 2018.",
        "Dr. Anil Rao prescribed metformin 500 mg twice daily.",
        "On 12 Aug, Dr. Rao said you have low blood sugar episodes and to not skip meals.",
        "According to your doctor, the ankle swelling is caused by amlodipine.",
    ],
)
def test_attributed_doctor_statements_pass_only_when_opted_in(text):
    assert is_diagnostic(text)
    assert not is_diagnostic(text, allow_attributed=True)


def test_opt_in_still_blocks_unattributed_sentences():
    text = "Dr. Rao said not to skip meals. You have diabetes."
    assert is_diagnostic(text, allow_attributed=True)


@pytest.mark.parametrize("text,flagged", [
    ("The label for glimepiride, which Dr. Rao prescribes for you, warns about low sugar.", False),
    ("Your doctor prescribed metformin in 2024.", False),
    ("Metformin (prescribed by Dr. Mehta) and amlodipine.", False),
    ("Both prescribers may not know about each other.", False),
    ("Shelcal, which Dr. Kapoor prescribed, is taken at 7.", False),
    ("Dr. Kapoor, who prescribed Shelcal, may want to know.", False),
    ("I would prescribe a lower dose.", True),
    ("This is commonly prescribed for diabetes.", True),
])
def test_naming_who_prescribed_is_not_prescribing(text, flagged):
    assert is_diagnostic(text) is flagged
