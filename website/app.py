#!/usr/bin/env python

from flask import Flask, render_template, request, redirect, url_for
import subprocess

app = Flask(__name__)

@app.route("/")
def main():
    url = request.args.get('url', '')
    if url == 'about:blank':
        url = ''
    done = request.args.get('done', False)
    return render_template('index.html', url=url, base=request.base_url, done=done)

@app.route("/action")
def action():
    url = request.args.get('url', '')
    if request.args.get('open', ''):
        subprocess.Popen("DISPLAY=:0 /home/pi/player/player.py '%s'" % url, shell=True)
    elif request.args.get('browser', ''):
        subprocess.Popen("DISPLAY=:0 xdg-open '%s'" % url, shell=True)
    return redirect(url_for('main', url=url, done=True))

if __name__ == "__main__":
    app.run(host='0.0.0.0', debug=True)
