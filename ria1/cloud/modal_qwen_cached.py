import time
import modal

app = modal.App("ria-qwen-cached-test")

MODEL_PATH = "/models/qwen2.5-3b"

volume = modal.Volume.from_name(
    "ria-qwen-model-cache"
)

image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.3.2-cudnn9-runtime-ubuntu22.04",
        add_python="3.11",
    )
    .pip_install(
        "torch>=2.5,<2.9",
        "transformers>=4.44,<5",
        "accelerate",
        "safetensors",
    )
)


@app.cls(
    image=image,
    gpu="T4",
    volumes={"/models": volume},
    timeout=300,
    min_containers=0,
    max_containers=1,
    single_use_containers=True,
)
class RiaModel:

    @modal.enter()
    def load(self):
        import torch
        from transformers import (
            AutoTokenizer,
            AutoModelForCausalLM,
        )

        start = time.perf_counter()

        print("Loading cached Qwen model...")

        self.tokenizer = AutoTokenizer.from_pretrained(
            MODEL_PATH,
            local_files_only=True,
        )

        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_PATH,
            dtype=torch.float16,
            device_map="cuda",
            local_files_only=True,
        )

        self.model.eval()

        print(
            "Model loading:",
            round(time.perf_counter() - start, 2),
            "seconds",
        )

    @modal.method()
    def chat(self, message):
        import torch

        messages = [
            {
                "role": "system",
                "content": (
                    "You are Ria, a friendly AI companion. "
                    "Reply naturally and briefly. "
                    "Do not invent real-time information."
                ),
            },
            {
                "role": "user",
                "content": message,
            },
        ]

        prompt = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
        ).to("cuda")

        start = time.perf_counter()

        with torch.inference_mode():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=100,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        new_tokens = outputs[0][
            inputs["input_ids"].shape[-1]:
        ]

        reply = self.tokenizer.decode(
            new_tokens,
            skip_special_tokens=True,
        ).strip()

        return {
            "reply": reply,
            "generation_seconds": round(
                time.perf_counter() - start, 2
            ),
        }


@app.local_entrypoint()
def main():
    print("Starting cached Qwen GPU test...")

    start = time.perf_counter()

    result = RiaModel().chat.remote(
        "Hi Ria! Give me one short guitar practice tip."
    )

    print("RIA:", result["reply"])
    print(
        "Generation time:",
        result["generation_seconds"],
        "seconds",
    )
    print(
        "Total round-trip:",
        round(time.perf_counter() - start, 2),
        "seconds",
    )
