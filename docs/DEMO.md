# News Streams by Language

> **Language Support Note**: Whisper's performance varies by language:
> - **Tier 1** (Excellent): English, German, Russian, Italian, Spanish
> - **Tier 2** (Good): French, Japanese, Korean
> - **Tier 3** (Less Reliable): Georgian, Arabic, Thai
>
> For Tier 3 languages, you may experience:
> - Slower processing times
> - Less accurate transcription
> - Occasional missing translations
> 
> To improve performance with Tier 3 languages:
> - Use the 'large' model: `-m large`
> - Increase beam size: `-b 5`
> - Consider using only transcription (remove `-bt`) if needed

## Arabic
- Al Jazeera Arabic - [Stream](https://live-hls-web-aja.getaj.net/AJA/index.m3u8)
- Al Jazeera Arabic HD - [Stream](https://live-hls-web-aja.getaj.net/AJA/01.m3u8)

```bash
python main.py -u https://live-hls-web-aja.getaj.net/AJA/index.m3u8 -la ar -bt -l 0.0.0.0
```

## Balkan Region
- Al Jazeera Balkans - [Stream](https://live-hls-web-ajb.getaj.net/AJB/index.m3u8)
- News24 Albania - [Stream](https://tv.balkanweb.com/news24/livestream/playlist.m3u8)

```bash
python main.py -u https://live-hls-web-ajb.getaj.net/AJB/index.m3u8 -la bs -bt -l 0.0.0.0
```

## English
- Al Jazeera Live - [Stream](https://live-hls-web-aje.getaj.net/AJE/index.m3u8)
- Bloomberg - [Stream](https://www.bloomberg.com/media-manifest/streams/phoenix-us.m3u8)
- CBS News - [Stream](https://dai.google.com/linear/hls/pa/event/Sid4xiTQTkCT1SLu6rjUSQ/stream/f0e1c801-cbb2-4244-90b6-c91bd21427a8:BRU/master.m3u8)
- DW English - [Stream](https://dwamdstream101.akamaized.net/hls/live/2015524/dwstream101/index.m3u8)
- DW English Mirror - [Stream](https://dwamdstream102.akamaized.net/hls/live/2015525/dwstream102/index.m3u8)

```bash
python main.py -u https://live-hls-web-aje.getaj.net/AJE/index.m3u8 -la en -l 0.0.0.0
```

## French
- BX1 - [Stream](https://59959724487e3.streamlock.net/stream/live/master.m3u8)

```bash
python main.py -u https://59959724487e3.streamlock.net/stream/live/master.m3u8 -la fr -bt -l 0.0.0.0
```

## Georgian
- 1TV Georgia - [Stream](https://tv.cdn.xsg.ge/gpb-1tv/index.m3u8)
- 2TV Georgia - [Stream](https://tv.cdn.xsg.ge/gpb-2tv/index.m3u8)

```bash
python main.py -u https://tv.cdn.xsg.ge/gpb-1tv/index.m3u8 -la ka -bt -l 0.0.0.0
```

## German
- R9 - [Stream](https://ms01.w24.at/R9/smil:liveeventR9.smil/playlist.m3u8)
- RTV - [Stream](http://iptv.rtv-ooe.at/stream.m3u8)
- W24 - [Stream](https://ms01.w24.at/W24/smil:liveevent.smil/playlist.m3u8)

```bash
python main.py -u https://ms01.w24.at/W24/smil:liveevent.smil/playlist.m3u8 -la de -bt -l 0.0.0.0
```

## Italian
- Rai News 24 - [Stream](http://wzstreaming.rai.it/TVlive/liveStream/playlist.m3u8)

```bash
python main.py -u http://wzstreaming.rai.it/TVlive/liveStream/playlist.m3u8 -la it -bt -l 0.0.0.0
```

## Romanian
- Aleph News - [Stream](https://stream-aleph.m.ro/Aleph/ngrp:Alephnewsmain.stream_all/playlist.m3u8)

```bash
python main.py -u https://stream-aleph.m.ro/Aleph/ngrp:Alephnewsmain.stream_all/playlist.m3u8 -la ro -bt -l 0.0.0.0
```

## Russian
- DW Russian - [Stream](https://dwamdstream110.akamaized.net/hls/live/2017971/dwstream110/index.m3u8)
- TV Rain - [Stream](https://wl.tvrain.tv/transcode/ses_1080p/playlist.m3u8)

```bash
python main.py -u https://wl.tvrain.tv/transcode/ses_1080p/playlist.m3u8 -la ru -bt -l 0.0.0.0
```

## Spanish
- DW Español - [Stream](https://dwamdstream104.akamaized.net/hls/live/2015530/dwstream104/index.m3u8)

```bash
python main.py -u https://dwamdstream104.akamaized.net/hls/live/2015530/dwstream104/index.m3u8 -la es -bt -l 0.0.0.0
```

Note: Some streams may require additional authentication or may not be available in all regions. The `-l 0.0.0.0` parameter binds the server to all network interfaces.