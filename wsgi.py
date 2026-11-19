# C:\aimlmini\wsgi.py
"""WSGI entry point. Used by the Flask dev server and by gunicorn in production."""
import os

# XGBoost pulls in numpy and scipy, and their BLAS backends reserve memory per
# thread. A single thread is enough for single row predictions and keeps the app
# usable on machines with limited free memory.
for _name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_name, "1")

from app import create_app

app = create_app()

if __name__ == "__main__":
    # The reloader starts a second process that loads the model again, which can
    # exhaust memory on a small machine, so it stays off.
    app.run(debug=True, use_reloader=False)
