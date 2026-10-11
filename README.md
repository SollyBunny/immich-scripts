# Immich Scripts

Some scripts that I use with my [Immich](https://immich.app/) instance

## Usage

1. Create and setup [Python virtual environment](https://docs.python.org/3/library/venv.html)

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

2. Create `.env`

```cfg
IMMICH_API_KEY=...
IMMICH_URL=...
SUS_THUMBNAIL_UUID=...
```

3. Run

```sh
./run-scripts.py
```
