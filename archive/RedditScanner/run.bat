@echo off
call .venv\Scripts\activate
python main.py --refresh --cache-ttl 1800
python -m streamlit run app.py
pause
