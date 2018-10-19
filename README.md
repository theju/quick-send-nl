# Quick Send Newsletter

A simple web interface to send out bulk emails like newsletters using an existing
SMTP server (like Sendgrid, AWS SES etc) or your Google account (through OAuth2).

It works in 3 steps:

1. Upload a CSV file with a header.
2. Compose a message (using the django template language for dynamic substitution).
3. Enter the SMTP details or authorize your Google account and send.

None of the data is retained in the database. It is deleted as soon as the emails
are sent out.

## Installation

1. Install the dependencies using `pipenv`_.
2. (Optional) If you plan to support sending emails through Google,
add and fill the following attribute in the `server/local.py`
   ```
   GOOGLE_OAUTH = {
       'CLIENT_ID': '...',
       'CLIENT_SECRET': '...'
   }
   ```
3. Add the Redis connection attribute to the `server/local.py`:
   ```
   REDIS = {
       'host': '...',
       'port': ...,
       'password': '...'
   }
   ```
4. Run the `rqworker` command to run the background queue (from the top-level project directory):
   ```
   DJANGO_SETTINGS_MODULE=server.settings rqworker --name <name_of_top_level_folder> --queue-class=app.utils.DjQueue --job-class=app.utils.DjJob
   ```
5. It is highly recommended that you create a new `SECRET_KEY` in your `server/local.py`.

## License

MIT License. Check the `LICENSE` file.
