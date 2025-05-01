# Motivation

Google Gemini 2.5 is currently best model to talk about your code,
available freely using Google AI Studio web interface.

But manually copy/pasting changes gets old quick so I vibe coded
this plugin to replace that process with automation.

# install local dependencies

apt install python3-flask python3-flask-cors

# start local server

python3 server.py

# load temporary add-on in firefox

# pack and send source code to model

zip /tmp/firefox-aistudio-plugin.zip $( git ls-files )

# Google AI Studio prompt

ALWAYS include full file content when changing files and filename.
ALWAYS add comment in first line which include filename with marker
@@FILENAME@@ filename.py

# git integration

If there is local git repository with files in it, server will
automatically update and commit changes.

It will not add new files, you have to do that manually.

# multiple projects in separate tabs

Plugin pop-up has option to specify server port (and server has --port
option) which allows you to have multiple sessions with AI Studio using
different ports.
