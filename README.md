# ha-aux-cloud

(**Currently work in progress**)

Unofficial integration for Aux Cloud connected appliances like air conditioners and heat pumps. Aux Cloud is a service based on the Broadlink platform that allows you to control your appliances from anywhere. This is a cloud alternative to [replacing wifi module in your AC](https://github.com/GrKoR/esphome_aux_ac_component), which will also allow you to control heat pumps. The implementation of API requests are based on public resources from Broadlink documentation and lots of reverse engineering.

## TODO

As the project is in early stage, there are a lot of things to do. Here is a list of tasks that need to be done:

- [x] Reverse egineer the Aux Cloud API
- [x] [API] Implement login
- [x] [API] Implement getting devices information
- [ ] [API] Implement updating device state
- [ ] [Home Assistant] Cloud data fetcher
- [ ] [Home Assistant] Data coordinator
- [ ] [Home Assistant] config flow
- [ ] [Home Assistant] climate entity
- [ ] [Home Assistant] sensor entity
- [ ] [Home Assistant] binary sensor entity
- [ ] [Home Assistant] number entity
- [ ] [Home Assistant] services
- [ ] Documentation
- [ ] Add to HACS
- [ ] Translations
