# PearPie-Win → Action1

Gebaseerd op het aangeleverde werkende Windows PearPie-script (`discover(1).py`)
en de eerder werkende DYMOConnect-Win Action1-processor.

## Installatie
Kopieer deze map naar de lokale Paromacs-recipes repository.
Maak vervolgens een override:

    autopkg make-override PearPie-Win.action1

Vul de bestaande Input-keys in:
- `PEARPIE_RELEASE_URL`: standaard ingesteld op `https://releases.pearpie.ai/beta/latest-win-x64-msi.json`.
- `ACTION1_BASE_URL`: Action1 API base URL (EU-waarde vooraf ingevuld).
- `ACTION1_ORG_ID`, `ACTION1_CLIENT_ID`, `ACTION1_CLIENT_SECRET`: eigen Action1-gegevens.
- `ACTION1_PACKAGE_NAME`: standaard `PearPie` (moet reeds bestaan in Action1).
- `ACTION1_DRY_RUN`: standaard `true`; pas na test wijzigen in `false`.

Test:

    autopkg run -v PearPie-Win.action1

## Werking
- Feed verwacht JSON-sleutels: `version`, `url`, `sha256`, `published_at`.
- Alleen Windows_64 MSI, conform het oorspronkelijke script.
- Downloads worden SHA-256-gecontroleerd en per versie in AutoPkg-cache opgeslagen.
- TLS wordt geverifieerd met `certifi` (werkt met AutoPkg Python zonder `requests`).
- Nieuwe Action1-versie erft installatieconfiguratie van de hoogste bestaande versie.
- `release_date` komt uit `published_at`.
- Bestaande versies worden niet opnieuw geüpload als de MSI-bestandsnaam al is geconfigureerd.
- Bij een gedeeltelijke upload wordt de ontbrekende MSI opnieuw geüpload.
- Dry-run wijzigt niets in Action1 (downloaden en verifiëren gebeurt wel).

## Belangrijk
Er is geen live test tegen de PearPie-feed of jouw Action1-tenant uitgevoerd.
De feed-URL staat nu standaard in beide recipes; een bestaande override kan deze waarde nog overschrijven.
Zet nooit echte client secrets in deze publieke recipes of in Git.
