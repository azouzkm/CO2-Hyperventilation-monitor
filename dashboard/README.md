# Dashboard (browser)

`index.html`, from the team's first commit: an alarm banner coloured by state (Normal, Advisory,
Critical, Technical) and the latest CO₂ value, polling the service's `/api/latest` once a second.

## Still to do

- Live CO₂ trace and breathing-rate trend (Chart.js or Plotly)
- An alarm sound for each state
- Registration page for message recipients (opt-in, with the consent timestamp stored)
- Have the service serve this page at <http://localhost:8000>
