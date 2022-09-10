# Project GPIO Recording Control

for Raspberry Pi

- uses GPIO for button to start and stop recording
- uses GPIO for status led
- manages pipeline with `arecord` and `lame` to generate `.mp3`
  recording with timestamp
- http server for status display with start and stop buttons
  (use e. g. `apache` with `ProxyPass` for authentication and tls)

# Dependencies

- commandline tools: `arecord`, `lame`
- javascript and css libraries: `jquery`, `bootstrap` (cdn), `bootstrap-sweetalert`

# TODO

- config file

