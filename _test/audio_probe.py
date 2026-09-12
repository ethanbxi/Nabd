import pyaudiowpatch as pa

p = pa.PyAudio()
try:
    wasapi = p.get_host_api_info_by_type(pa.paWASAPI)
    spk = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
    print("default output :", spk["name"])

    lb = None
    for d in p.get_loopback_device_info_generator():
        if spk["name"] in d["name"]:
            lb = d
            break

    if not lb:
        print("loopback match : NONE")
    else:
        print("loopback match :", lb["name"])
        print("rate           :", int(lb["defaultSampleRate"]), "Hz")
        print("channels       :", lb["maxInputChannels"])

        # Actually open it and pull audio to prove it works.
        rate = int(lb["defaultSampleRate"])
        ch = lb["maxInputChannels"]
        s = p.open(format=pa.paInt16, channels=ch, rate=rate,
                   input=True, input_device_index=lb["index"],
                   frames_per_buffer=1024)
        peak = 0
        got = 0
        for _ in range(int(rate / 1024 * 2)):  # ~2 seconds
            data = s.read(1024, exception_on_overflow=False)
            got += len(data)
            for i in range(0, len(data), 512):
                chunk = data[i:i + 2]
                if len(chunk) == 2:
                    v = int.from_bytes(chunk, "little", signed=True)
                    peak = max(peak, abs(v))
        s.close()
        print("captured bytes :", got)
        print("peak amplitude :", peak, "(0 = silence was playing, that's OK)")
        print("RESULT         : LOOPBACK OK")
finally:
    p.terminate()

