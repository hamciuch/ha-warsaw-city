# v0.2.2 options-flow fix

Patch changes:
- safer line selection after choosing a stop post
- catches API errors instead of Home Assistant generic "Unknown error occurred"
- uses a simpler multi-select selector compatible with more HA versions
- version bumped to 0.2.2

Copy files over `custom_components/warsaw_city/`, restart Home Assistant, and retry adding the stop.
