from http.server import BaseHTTPRequestHandler
import sys
import traceback

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        errors = []

        try:
            import fastapi
            errors.append("fastapi: OK")
        except Exception as e:
            errors.append("fastapi: FAIL - {}".format(e))

        try:
            import sqlalchemy
            errors.append("sqlalchemy: OK")
        except Exception as e:
            errors.append("sqlalchemy: FAIL - {}".format(e))

        try:
            import psycopg2
            errors.append("psycopg2: OK")
        except Exception as e:
            errors.append("psycopg2: FAIL - {}".format(e))

        try:
            import telegram
            errors.append("telegram: OK")
        except Exception as e:
            errors.append("telegram: FAIL - {}".format(e))

        try:
            import matplotlib
            errors.append("matplotlib: OK")
        except Exception as e:
            errors.append("matplotlib: FAIL - {}".format(e))

        try:
            import google.generativeai
            errors.append("google-generativeai: OK")
        except Exception as e:
            errors.append("google-generativeai: FAIL - {}".format(e))

        try:
            from app import app as fastapi_app
            errors.append("app import: OK")
        except Exception as e:
            errors.append("app import: FAIL - {}".format(traceback.format_exc()))

        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write("\n".join(errors).encode())
