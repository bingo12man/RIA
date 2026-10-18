from mlx_lm import load, generate

MODEL = "mlx-community/Qwen3-1.7B-4bit"
ADAPTER = "ria1/adapters/comprehension_pilot_001"

SYSTEM = (
    "You understand Tamil written in English letters "
    "(Tanglish). Translate the current user's meaning "
    "into one concise English sentence. "
    "Do not answer their request."
)

TESTS = [
    "Enakku coffee vendaam, tea podhum.",
    "Enakku tea vendaam, coffee podhum.",
    "Naan inniku office-ku pogala.",
    "Enakku konjam bayama irukku.",
]

for label, adapter in [
    ("BASE", None),
    ("LORA", ADAPTER),
]:
    print("\n" + "=" * 60)
    print("MODEL:", label)

    model, tokenizer = load(
        MODEL,
        adapter_path=adapter,
    )

    for sentence in TESTS:
        messages = [
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": "Current user: " + sentence,
            },
        ]

        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False,
        )

        result = generate(
            model,
            tokenizer,
            prompt=prompt,
            max_tokens=100,
            verbose=False,
        )

        print("\nINPUT:", sentence)
        print("OUTPUT:", result)

    del model
    del tokenizer
