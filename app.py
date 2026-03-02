from flask import Flask, request, jsonify, render_template
from pymongo import MongoClient
from datetime import datetime
import os

app = Flask(__name__)

# MongoDB connection
client = MongoClient("mongodb://localhost:27017/")  # or use MongoDB Atlas URI
db = client["github_events"]
collection = db["events"]

def format_timestamp(iso_string):
    """Convert ISO timestamp to readable UTC format"""
    dt = datetime.strptime(iso_string, "%Y-%m-%dT%H:%M:%SZ")
    suffix = lambda d: "th" if 11<=d<=13 else {1:"st",2:"nd",3:"rd"}.get(d%10,"th")
    return dt.strftime(f"%-d{suffix(dt.day)} %B %Y - %-I:%M %p UTC")

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json
    event_type = request.headers.get("X-GitHub-Event")
    document = {}

    if event_type == "push":
        document = {
            "request_id": data["after"],           # Git commit hash
            "author": data["pusher"]["name"],
            "action": "PUSH",
            "from_branch": None,
            "to_branch": data["ref"].split("/")[-1],  # e.g., refs/heads/main → main
            "timestamp": format_timestamp(data["head_commit"]["timestamp"].replace("+00:00", "").split("+")[0].split("Z")[0] + "Z" if "Z" not in data["head_commit"]["timestamp"] else data["head_commit"]["timestamp"])
        }

    elif event_type == "pull_request":
        pr = data["pull_request"]
        action = data["action"]

        if action == "closed" and pr.get("merged"):
            # MERGE event
            document = {
                "request_id": str(pr["id"]),
                "author": pr["user"]["login"],
                "action": "MERGE",
                "from_branch": pr["head"]["ref"],
                "to_branch": pr["base"]["ref"],
                "timestamp": format_timestamp(pr["merged_at"].replace("+00:00",""))
            }
        elif action == "opened" or action == "reopened":
            # PULL REQUEST event
            document = {
                "request_id": str(pr["id"]),
                "author": pr["user"]["login"],
                "action": "PULL_REQUEST",
                "from_branch": pr["head"]["ref"],
                "to_branch": pr["base"]["ref"],
                "timestamp": format_timestamp(pr["created_at"].replace("+00:00",""))
            }

    if document:
        collection.insert_one(document)
        return jsonify({"status": "stored"}), 200

    return jsonify({"status": "ignored"}), 200


@app.route("/events", methods=["GET"])
def get_events():
    """API endpoint polled by UI every 15 seconds"""
    events = list(collection.find({}, {"_id": 0}).sort("_id", -1).limit(20))
    formatted = []
    for e in events:
        if e["action"] == "PUSH":
            msg = f'"{e["author"]}" pushed to "{e["to_branch"]}" on {e["timestamp"]}'
        elif e["action"] == "PULL_REQUEST":
            msg = f'"{e["author"]}" submitted a pull request from "{e["from_branch"]}" to "{e["to_branch"]}" on {e["timestamp"]}'
        elif e["action"] == "MERGE":
            msg = f'"{e["author"]}" merged branch "{e["from_branch"]}" to "{e["to_branch"]}" on {e["timestamp"]}'
        else:
            continue
        formatted.append({"message": msg, "action": e["action"]})
    return jsonify(formatted)


@app.route("/")
def index():
    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True, port=5001)