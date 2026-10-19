# Trade design variants

Site Magic now has three local, schema-addressable design directions inspired by
the interaction patterns in OriginKit. They are recreations, not copied
OriginKit components or runtime dependencies.

| ID | Direction | Best fit | Composition |
| --- | --- | --- | --- |
| `workshop-contrast` | dark ink, safety orange, hard-edged utility | HVAC, electrical, roofing, garage door | split hero, service tiles, proof rail |
| `field-notebook` | warm paper, forest green, editorial confidence | landscaping, tree service, cleaning, remodeling | editorial hero, service cards, story proof |
| `after-hours` | midnight navy, ice blue, copper emergency accent | plumbing, restoration, emergency HVAC | stacked hero, availability band, short lead form |

Select one with the optional `designVariant` property in `SiteSpec`. The
variant controls composition and visual tokens only; copy, claims, imagery,
and business facts still come from verified tenant inputs.

The schema is `schemas/design-variants.json` and the source record is
`schemas/design-variant-catalog.json`. Any later renderer
implementation must vendor reviewed source and pass the existing accessibility,
performance, provenance, and tenant-isolation gates.
