# ... imports ...

submit_bp = Blueprint('submit_bp', __name__)

@submit_bp.route('/submit_code', methods=['POST'])
def submit_code_route():
    config = current_app.config['APP_CONFIG']
    request_lock = current_app.config['REQUEST_LOCK']

    # ---> Current lock acquisition <---
    if not request_lock.acquire(blocking=False):
        print("W: Request rejected, server busy (lock acquisition failed).", file=sys.stderr) # Add log here
        return jsonify({'status': 'error', 'message': 'Server busy, please try again shortly.'}), 429
    # ---> If lock acquired, proceeds below <---
    try:
        # ... rest of the processing logic ...
        pass
    except Exception as e:
        # ... error handling ...
        pass
    finally:
        # ---> Lock release <---
        if request_lock.locked(): request_lock.release()
# ... rest of file ...
# @@FILENAME@@ routes/submit.py