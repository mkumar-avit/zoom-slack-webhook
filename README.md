# zoom-slack-webhook (Zoom to Slack webhook events)
This code takes webhook events from Zoom (conferencing app) and translates and formats it to display on a Slack Channel (messaging app).   The code is designed around the use of AWS Lambda (with a AWS API Gateway).  This may be useful for enterprise accounts that want to monitor activity on their Zoom account like new user creation, license usage, issues with webinars, and global account changes.


The code does use the Python requests library, which is not native to AWS Lambda Python 3.7 and it requires importing the Python library into the Lambda environment.  The files can be zipped up and imported directly into an AWS Lambda Python function.   In configuring the Lambda function set the max run time to 6 seconds (multiple lookup calls to zoom can increase the time to up to a little more than 5 seconds).

The code takes advantage of AWS Lambda environmental variables for the following items:
- JWTToken - This is obtained from Zoom by creating a new JWT app in Zoom and allows for group and user lookup
- bearerToken -	This is to validate the webhook event is a valid and authorized message
- debugMode	- enables error messages to be sent to Slack within a code block message
- slackHookPath - This is obtained from Slack via their webhook app option
- timezone - Set to the correct timezone phrase (i.e. U.S./Pacific) to format time correctly in the Slack message


## App Requirements
- **Zoom JWT Token** via a simple custom app created in Zoom's marketplace (the expiration date of the JWT token is configurable)
- **Zoom Webhook Only App**  a simple custom app also created in Zoom's marketplace made with a few clicks.  From this zoom app, an admin can select what notifications they want pushed to Slack
- **AWS** - AWS Lambda and an API Gateway at a minimum configured with appropriate IAM permissions so they can communicate with each other.  Cloudwatch is useful for logging all data coming into AWS Lambda

## General Program Architecture 
![Alt text](https://github.com/mkumar-avit/zoom-slack-webhook/blob/master/zoom%20webhook.png?raw=true "Application Diagram")

## Sample Output in Slack
![Alt text](https://github.com/mkumar-avit/zoom-slack-webhook/blob/master/Zoom-Slack-Webhook%20preview.png?raw=true "Slack sample")
