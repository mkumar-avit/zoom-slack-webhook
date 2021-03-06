# zoom-slack-webhook event notification 
#### Zoom Webhook events displayed in a Slack channel
This code takes webhook events from Zoom (conferencing app) and translates and formats it to display on a Slack Channel (messaging app).   The code is designed around the use of AWS Lambda (with an AWS API Gateway).  This may be useful for enterprise accounts that want to monitor activity on their Zoom account like new user creation, license usage, issues with webinars, and global account changes.


The code does use the Python requests library, which is not native to AWS Lambda Python 3.7 and it requires importing the Python library into the Lambda environment.  The program also uses pyJWT module to generate a JWT token.  The files can be zipped up and imported directly into an AWS Lambda Python function.   In configuring the Lambda function set the max run time to 6 seconds (multiple lookup calls to zoom can increase the time to up to a little more than 5 seconds).

The code takes advantage of AWS Lambda environmental variables that needed to be populated by the user for the following items:
- apiKey & apiSecret - These are obtained from Zoom by creating a new JWT app in Zoom and allows for group and user lookup.  It is not required for the webhook events to post to Slack, but items like host ID and user ID will not be translated to an actual user name, or a license count will not display when a new user event is triggered.
- bearerToken -	This is to validate the webhook event is a valid and authorized message
- debugMode	- enables error messages to be sent to Slack within a code block message
- slackHookPath - This is obtained from Slack via their webhook app option
- timezone - Set to the correct timezone phrase (i.e. U.S./Pacific) to format time correctly in the Slack message


## App Requirements
- **Zoom JWT App** A custom app created in Zoom's marketplace
- **Zoom Webhook Only App**  a simple custom app also created in Zoom's marketplace made with a few clicks.  From this Zoom app, an admin can select what notifications they want pushed to Slack
- **AWS** - AWS Lambda and an API Gateway at a minimum configured with appropriate IAM permissions so they can communicate with each other.  Cloudwatch is useful for logging all data coming into AWS Lambda. An S3 bucket will be needed for logging and tracking of data to create licensed user creation trend graphs (via CSV file).

## General Program Architecture 
![Alt text](https://github.com/mkumar-avit/zoom-slack-webhook/blob/master/Zoom%20AWS%20Slack.png?raw=true "AWS Application Diagram")

## Sample Output in Slack
![Alt text](https://github.com/mkumar-avit/zoom-slack-webhook/blob/master/Zoom-Slack-Webhook%20preview.png?raw=true "Slack sample")
