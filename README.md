# MIRROR — AI Disaster Consequence Simulator

An offline-first Streamlit hackathon demo for exploring disaster-response decisions.

## Run

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

The app uses a hybrid architecture: a world model creates zones, hospitals and access constraints; deterministic prediction rules simulate consequences; an optimizer allocates scarce resources; and a generated briefing explains only the calculated results. No API key is required.
