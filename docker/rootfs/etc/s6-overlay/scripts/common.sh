# Shared by the start scripts. Settings filled in by proxium-init reach the services through with-contenv.

PROXIUM_DATA=/var/lib/proxium
CONTAINER_ENV=/run/s6/container_environment

# Whether PROXIUM_SERVICES has the given one: proxy, api or admin.
service_enabled() {
  case ",${PROXIUM_SERVICES}," in
    *",$1,"*) return 0 ;;
    *) return 1 ;;
  esac
}

# Stays down for good: s6 doesn't restart it. For services turned off by the settings.
stay_down() {
  s6-svc -O .
  exit 0
}
