# zoom-slack-webhook
This code takes certain webhook events from Zoom (conferencing app) and translates and formats it to display on a Slack Channel (messaging app).   The code is designed around the use of AWS Lambda (with a AWS API Gateway).  This may be useful for enterprise accounts that want to monitor activity on their Zoom account like new user creation, license usage, issues with webinars, and global account changes.


The code does use the Python requests library, which is not native to AWS Lambda Python 3.7 and it requires importing the Python library into the Lambda environment.
