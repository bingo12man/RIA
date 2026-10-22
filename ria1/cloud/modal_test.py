import modal

app = modal.App("ria-cloud-test")

@app.function()
def hello():
    return "Hello from RIA's cloud backend!"

@app.local_entrypoint()
def main():
    print(hello.remote())
