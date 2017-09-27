import enum


class AirplaneType(enum.Enum):
    unknown = 0
    glider = 1
    tow_plane = 2
    helicopter_rotorcraft = 3
    parachute = 4
    drop_plane = 5
    hang_glider = 6
    paraglider = 7
    powered_aircraft = 8
    jet_aircraft = 9
    ufo = 10
    baloon = 11
    airship = 12
    uav = 13
    static_object = 15


class AddressType(enum.Enum):
    unknown = 0b000
    icao = 0b001
    flarm = 0b010
    ogn_tracker = 0b011
    naviter = 0b100


class BeaconType(enum.Enum):
    aircraft_beacon = 1
    server_beacon = 2
    server_status = 3
