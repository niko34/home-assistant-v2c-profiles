# V2C Profiles for Home Assistant

A custom Home Assistant integration for reading and selecting V2C Trydan
charging profiles from V2C Cloud.

> [!IMPORTANT]
> This is an independent community project. It is not affiliated with or
> endorsed by V2C.

## Features

- Creates a `select` entity containing the profiles returned by V2C Cloud.
- Tracks the currently active charging profile.
- Refreshes profile data every 60 seconds.
- Uses V2C's rotating OAuth refresh tokens.
- Persists each rotated refresh token immediately in the Home Assistant config
  entry.
- Rebuilds a broken refresh-token chain automatically with the stored V2C
  login.
- Supports credential replacement through Home Assistant's reauthentication
  flow.

## Safety

- Setup performs a read-only profile request and OAuth authentication.
- Setup never activates a charging profile.
- A profile is activated only after an explicit selection on the `select`
  entity.
- Credentials and tokens are never exposed as entity state or written to the
  integration logs.

Home Assistant stores the V2C API key, email address, password, and refresh
token in its config entry storage. Access to that storage should be restricted
in the same way as the rest of your Home Assistant configuration.

## Installation with HACS

1. Open HACS in Home Assistant.
2. Open **Integrations** and select **Custom repositories** from the menu.
3. Add `https://github.com/niko34/home-assistant-v2c-profiles` as an
   **Integration** repository.
4. Install **V2C Profiles**.
5. Restart Home Assistant.

## Manual installation

1. Copy `custom_components/v2c_profiles` into Home Assistant's
   `/config/custom_components/` directory.
2. Validate the Home Assistant configuration.
3. Restart Home Assistant.

## Configuration

Open **Settings → Devices & services → Add integration → V2C Profiles**.

Enter:

- the charging station ID;
- the V2C API key;
- the V2C account email address;
- the V2C account password.

The integration validates access without changing the active profile. The
first OAuth refresh token is then stored alongside the login so the integration
can recover automatically if token rotation is interrupted.

## Disclaimer

The V2C Cloud endpoints used by this project are not documented as a public,
stable third-party API and may change without notice. Use this integration at
your own risk.

## License

[MIT](LICENSE)
