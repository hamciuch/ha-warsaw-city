# v0.2.3 — correct ZTM line/departure API calls

The previous code incorrectly called `get_ztm_odjazdy_linii_z_przystanku`
without the required JSON body.

New API flow:
1. `get_ztm_lista_linii_na_przystanku`
   body: `{"busstopId":"...","busstopNr":"..."}`
2. For every selected line:
   `get_ztm_odjazdy_linii_z_przystanku`
   body: `{"busstopId":"...","busstopNr":"...","line":"..."}`

Overwrite the matching files in `custom_components/warsaw_city/`,
restart Home Assistant and retry the stop configuration.
