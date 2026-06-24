import os
from flask import Flask

app = Flask(__name__)

@app.route("/")
def home():
    return "Hello World from team It works on my machine! (tested by Tommi)"

@app.route("/health")
def health():
    return {"status": "ok"}, 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)