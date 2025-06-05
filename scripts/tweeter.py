import tweepy 
from tweepy import OAuth2UserHandler

client_id = "YOUR_CLIENT_ID"
client_secret = "YOUR_CLIENT_SECRET"
redirect_uri = "https://walmart.com"

oauth2_user_handler = tweepy.OAuth2UserHandler(
    client_id=client_id,
    redirect_uri=redirect_uri,
    scope=["tweet.read", "tweet.write", "users.read", "offline.access"],
    client_secret=client_secret
)

print(oauth2_user_handler.get_authorization_url())

# After visiting the URL and authorizing, paste the full redirect URL:
authorization_response = input("Paste the callback URL: ")

access_token = oauth2_user_handler.fetch_token(authorization_response)

client = tweepy.Client(access_token["access_token"])
response = client.create_tweet(text="This Tweet was Tweeted using Tweepy and Twitter API v2!")
print(response)
