
from indic_transliteration import sanscript

TESTS = [
    "Amma inniku veetukku varala",
    "Amma inniku veetukku pogala",
    "Naan naalaikku college-ku varuven",
    "Naan naalaikku college-ku poven",
    "Avalukku indha food vendaam",
    "Indha alavu saapadu podhum",
    "Nethu avan call pannala",
    "Inniku enakku velai mudiyala",
    "Naalaikku vara mudiyuma",
    "Aval konjam kovama irukka",
    "Enakku ippo pesa thonala",
    "Avan vara maattennu sonnaan",
]

print("\nRIA-1 LIGHTWEIGHT TRANSLITERATION TEST")
print("=" * 55)

for i, sentence in enumerate(TESTS, 1):
    try:
        result = sanscript.transliterate(
            sentence,
            sanscript.ITRANS,
            sanscript.TAMIL,
        )

        print(f"\nTEST {i}")
        print("TANGLISH:", sentence)
        print("TAMIL:", result)

    except Exception as error:
        print(f"TEST {i} ERROR:", error)

