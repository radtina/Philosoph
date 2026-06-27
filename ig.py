import json

FOLLOWERS_FILE = "followers.json"
FOLLOWING_FILE = "following.json"
OUTPUT_FILE = "not_following_you_back.txt"


def load_followers(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    followers = set()
    for entry in data:
        for item in entry.get("string_list_data", []):
            followers.add(item["value"].lower())

    return followers


def load_following(path):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    following = set()
    for entry in data.get("relationships_following", []):
        username = entry.get("title")
        if username:
            following.add(username.lower())

    return following


def main():
    followers = load_followers(FOLLOWERS_FILE)
    following = load_following(FOLLOWING_FILE)

    # CORE LOGIC (THIS IS THE IMPORTANT LINE)
    not_following_back = sorted(following - followers)

    print(f"\nFound {len(not_following_back)} accounts you follow that do NOT follow you back:\n")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        for username in not_following_back:
            link = f"https://www.instagram.com/{username}"
            print(link)
            f.write(link + "\n")

    print(f"\nSaved clickable links to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
