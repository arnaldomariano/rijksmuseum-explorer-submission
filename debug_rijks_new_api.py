from rijks_api import _get_session, resolve_objectnumber_to_pid, build_representations

session = _get_session()

pid = resolve_objectnumber_to_pid(session, "SK-A-4050")
urls = build_representations(pid)

print("PID:", pid)
print("Schema:", urls["schema_json"])
print("LinkedArt:", urls["linkedart_jsonld"])
