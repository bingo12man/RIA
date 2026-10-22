import time
import modal

app = modal.App("ria-qwen-test")

MODEL_ID = "Qwen/Qwen2.5-3B-Instruct"

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
    timeout=600,
    min_containers=0,
    max_containers=1,
    single_use_containers=True,
)
class RiaModel:

    @modal.enter()
    def load_model(self):
        import torch
        from transformers import (
            AutoTokenizer,
            AutoModelForCausalLM,
        )

        print("Loading Qwen onto the cloud GPU...")

        self.tokenizer = AutoTokenizer.from_pretrained(
            MODEL_ID
        )

        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.float16,
            device_map="cuda",
        )

        self.model.eval()
        print("RIA model loaded successfully.")

    @modal.method()
    def chat(self, message: str):
        import torch

        messages = [
            {
                "role": "system",
                "content": (
                    "You are Ria, a friendly AI desk companion. "
                    "Give short, natural responses. "
                    "Do not claim to have live information."
                ),
            },
            {
                "role": "user",
                "content": message,
            },
        ]

        inputs = self.tokenizer.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_tensors="pt",
        ).to("cuda")

        start = time.perf_counter()

        with torch.inference_mode():
            outputs = self.model.generate(
                inputs,
                max_new_tokens=100,
                do_sample=False,
                pad_token_id=self.tokenizer.eos_token_id,
            )

        response_tokens = outputs[0][
            inputs.shape[-1]:
        ]

        reply = self.tokenizer.decode(
            response_tokens,
            skip_special_tokens=True,
        ).strip()

        return {
            "model": MODEL_ID,
            "reply": reply,
            "generation_seconds": round(
                time.perf_counter() - start, 2
            ),
        }


@app.local_entrypoint()
def main():
    print("Starting one RIA cloud GPU test...")

    start = time.perf_counter()

    result = RiaModel().chat.remote(
        "Hi Ria! I'm learning guitar. Give me one short practice tip."
    )

    print("\nMODEL:", result["model"])
    print("RIA:", result["reply"])
    print(
        "Generation time:",
        result["generation_seconds"],
        "seconds",
    )
    print(
        "Total cloud round-trip:",
        round(time.perf_counter() - start, 2),
        "seconds",
    )
