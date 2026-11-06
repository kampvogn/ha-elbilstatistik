# Elbilstatistik til Home Assistant

Slå en dansk nummerplade op direkte i Home Assistant og få mærke, model (med pæne visningsnavne), farve, brændstof (el eller ej), status og første registreringsdato. Fx "Hvid Tesla Model 3 (el) i indkørslen", når dit Frigate-kamera læser en nummerplade.

Data kommer fra det offentlige API på [elbilstatistik.dk](https://api.elbilstatistik.dk/) og stammer fra Motorstyrelsens motorregister (DMR). Opsætningen foregår helt i Home Assistants brugerflade; du skal ikke skrive YAML for at sætte integrationen op.

## Installation

### Med HACS (anbefalet)

1. Åbn HACS i Home Assistant, vælg de tre prikker øverst til højre og **Brugerdefinerede repositories** (Custom repositories).
2. Indsæt `https://github.com/kampvogn/ha-elbilstatistik`, vælg typen **Integration** og tryk **Tilføj**.
3. Find **Elbilstatistik** i HACS, tryk **Download**, og genstart Home Assistant.


### Manuelt

Kopiér mappen `custom_components/elbilstatistik` til `custom_components/elbilstatistik` i din Home Assistant-konfigurationsmappe (dér hvor `configuration.yaml` ligger), og genstart Home Assistant.

## Opsætning

1. **Indstillinger > Enheder og tjenester > Tilføj integration > Elbilstatistik**.
2. Indtast din API-nøgle, eller lad feltet stå tomt for at køre uden nøgle.
3. Under **Konfigurér** på integrationen kan du ændre:
   - **Cache-tid** (standard 24 timer): samme plade slås kun op én gang i det tidsrum, også hvis den ikke findes. Dataene opdateres kun én gang om ugen.
   - **Ret læsefejl (fuzzy)** (standard til): retter typiske kameralæsefejl (0/O, 1/I, 8/B, 5/S, 2/Z, 6/G), så en plade, som kameraet har læst forkert, alligevel findes. Gælder ikke personlige nummerplader.

### Kvoter og API-nøgle

| | Opslag |
|---|---|
| Uden nøgle | 50 om dagen pr. internetadresse |
| Med gratis nøgle | 3.000 om måneden |

Opret en gratis nøgle på <https://api.elbilstatistik.dk/account/>. Er kvoten brugt op, holder integrationen pause, indtil API'et siger, at der igen er plads (det står i loggen én gang), og servicen giver en fejl i mellemtiden. Cachen gør, at et kamera, der ser den samme bil mange gange, kun koster ét opslag pr. døgn.

### Privatliv

Når du slår en plade op, sendes selve pladenummeret (og din API-nøgle, hvis du har en) til `api.elbilstatistik.dk`. Der findes ingen ejer- eller brugeroplysninger i data: kun oplysninger om selve køretøjet, som de står i DMR. Hvis det er et problem for dig, at pladenumre forlader dit hjem, skal du ikke bruge integrationen.

## Hvad du får

**Service `elbilstatistik.lookup_plate`** (felter: `plate`, valgfri `fuzzy`) returnerer:

| Felt | Eksempel |
|---|---|
| `plate` | `AB12345` |
| `found` | `true` / `false` |
| `make`, `model`, `variant` | `Tesla`, `Model 3`, `Long Range` |
| `colour` | `Hvid` |
| `fuel`, `is_electric` | `El`, `true` |
| `status` | `Registreret` |
| `first_registration`, `model_year` | `2021-03-04`, `2021` |
| `vehicle_type` | `Personbil` |
| `data_date` | `2026-11-01` (dataenes dato; opdateres ugentligt) |
| `match` | `exact`, eller `fuzzy` når kameraets aflæsning blev rettet (0/O, 1/I osv.) for at finde bilen |

Er pladen ikke i registret (eller bilen er afmeldt), er `found` `false`, og de øvrige felter er tomme.

**Begivenhed `elbilstatistik_vehicle`** udløses ved hvert opslag med de samme felter, så du kan lave en automatisering med udløseren "Begivenhed" uden at kalde servicen selv.

**Sensor "Seneste køretøj"**: tilstanden er fx `Tesla Model 3` (eller `Ukendt`), og felterne ovenfor er attributter. Sensoren opdateres kun af opslag; den ringer ikke selv til API'et.

## Eksempel 1: Frigate nummerpladegenkendelse

Forudsætter **Frigate 0.16 eller nyere** med *License Plate Recognition* slået til og MQTT sat op mellem Frigate og Home Assistant (den almindelige Frigate-integration). Frigate udgiver hver genkendt plade på MQTT-emnet `frigate/tracked_object_update` med `"type": "lpr"` og felterne `plate`, `score`, `camera` og `name` (`name` er kun sat, hvis pladen er en kendt plade i Frigates egen opsætning). Kilde: Frigates dokumentation for [License Plate Recognition](https://docs.frigate.video/configuration/license_plate_recognition/) og [MQTT](https://docs.frigate.video/integrations/mqtt/) (version 0.18-dokumentationen; eksemplet er ikke afprøvet mod en kørende Frigate). Tjek feltnavnene mod din egen version, hvis noget ikke virker, fx i **Udviklerværktøjer > MQTT > Lyt efter** på `frigate/tracked_object_update`.

Indsæt i **Indstillinger > Automatiseringer > Opret > Rediger i YAML** og ret kameranavn og `notify`-tjeneste:

```yaml
alias: Hvilken bil er i indkørslen?
mode: single
triggers:
  - trigger: mqtt
    topic: frigate/tracked_object_update
conditions:
  - condition: template
    value_template: >
      {{ trigger.payload_json.type == 'lpr'
         and trigger.payload_json.camera == 'driveway'
         and trigger.payload_json.plate }}
actions:
  - action: elbilstatistik.lookup_plate
    data:
      plate: "{{ trigger.payload_json.plate }}"
    response_variable: bil
  - condition: template
    value_template: "{{ bil.found }}"
  - action: notify.notify          # ret til din egen notify-tjeneste
    data:
      title: Bil i indkørslen
      message: >
        {{ bil.colour }} {{ bil.make }} {{ bil.model }}
        {{ '(el)' if bil.is_electric else '(' ~ bil.fuel | lower ~ ')' }}
        i indkørslen
  - delay: "00:01:00"              # undgå flere beskeder for samme bil
```

Ældre Home Assistant-versioner (før 2024.10; integrationen selv kræver 2024.11 eller nyere) bruger `platform:` i stedet for `trigger:`, og `trigger:`/`action:` i stedet for `triggers:`/`actions:`; opdatér Home Assistant, hvis YAML'en afvises. Ret `driveway` til kameraets navn i Frigate.

### Prøv uden kamera

Automatiseringen reagerer kun på MQTT-beskeden, så du kan prøve den uden et kamera, der ser nummerplader: gå til **Indstillinger > Enheder og tjenester > MQTT > Konfigurer**, og udgiv under **Udgiv en pakke** på emnet `frigate/tracked_object_update` en besked som Frigates (brug fx din egen bils nummerplade og dit kameranavn):

```json
{"type": "lpr", "camera": "driveway", "plate": "AB12345", "score": 0.92, "name": null}
```

Så kører automatiseringen præcis, som når Frigate genkender pladen. Prøv også at skrive pladen med en typisk kamerafejl (fx `A812345`): med fuzzy-søgning slået til finder integrationen stadig bilen, og feltet `match` er da `fuzzy`.

Vil du ikke kalde servicen, kan du i stedet bruge begivenheden `elbilstatistik_vehicle` som udløser og læse `trigger.event.data.make` osv.

## Eksempel 2: Manuelt (tekstfelt og knap)

Opret en hjælper **Tekst** (Indstillinger > Enheder og tjenester > Hjælpere) med navnet `Plade` (`input_text.plade`), og en automatisering, som du kan sætte på et dashboard med en knap:

```yaml
alias: Slå plade op
triggers:
  - trigger: state
    entity_id: input_button.slaa_plade_op   # hjælper af typen Knap
actions:
  - action: elbilstatistik.lookup_plate
    data:
      plate: "{{ states('input_text.plade') }}"
    response_variable: bil
  - action: persistent_notification.create
    data:
      title: "{{ bil.plate }}"
      message: >
        {% if bil.found %}
        {{ bil.colour }} {{ bil.make }} {{ bil.model }} {{ bil.variant }},
        {{ bil.fuel }}, første registrering {{ bil.first_registration }}
        {% else %}
        Pladen findes ikke i registret.
        {% endif %}
```

Du kan også prøve servicen under **Udviklerværktøjer > Handlinger** (vælg "Slå nummerplade op").

## Fejlfinding

- *"Kvoten er brugt op"*: vent, eller opret en gratis nøgle (se ovenfor) og tilføj den: fjern integrationen og tilføj den igen med nøglen.
- *Pladen findes ikke*: bilen kan være afmeldt, eller kameraet har læst forkert. Slå "Ret læsefejl" til.
- Fejl i logningen findes under **Indstillinger > System > Logs**; API-nøglen skrives aldrig i loggen.

---

## English

Look up a Danish license plate from Home Assistant: make, model (clean display names), colour, fuel/electric, status and first registration, via the public API of [elbilstatistik.dk](https://api.elbilstatistik.dk/) (data from the Danish Motor Vehicle Register, DMR; no owner data).

- Install via HACS (custom repository `https://github.com/kampvogn/ha-elbilstatistik`, type Integration) or copy `custom_components/elbilstatistik` manually. Set up under Settings > Devices & services; no YAML.
- An API key is optional. Without: 50 lookups per day per IP address. With a free key from <https://api.elbilstatistik.dk/account/>: 3,000 per month.
- Service `elbilstatistik.lookup_plate` (`plate`, optional `fuzzy`) returns `plate, found, make, model, variant, colour, fuel, is_electric, status, first_registration, model_year, vehicle_type, data_date, match` (`exact`/`fuzzy`), fires the event `elbilstatistik_vehicle` with the same data and updates the sensor "Last vehicle".
- Results are cached per plate (default 24 h, also "not found"); on HTTP 429 lookups pause until `Retry-After` has passed.
- Frigate example above: needs Frigate 0.16+ with LPR and MQTT; it listens to `frigate/tracked_object_update` (`type: lpr`).
- Privacy: the plate (and your key, if set) is sent to api.elbilstatistik.dk. The data contains no owner information.
