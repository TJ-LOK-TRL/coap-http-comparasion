# CoAP Service Discovery & Benchmarking — Self-Contribution Demo
### Project: Exploring the CoAP Protocol and Standard Endpoints for Lightweight Service Discovery in Wi-Fi Networks

---

## Overview

This demo is the practical self-contribution for the research project on CoAP (Constrained Application Protocol). It is divided into three modules of increasing complexity, each producing measurable results that feed directly into the written report.

---

## Module B — Automatic Service Discovery via Multicast (Core Demo)

**Goal:** Simulate a real IoT Wi-Fi environment where a CoAP client has no prior knowledge of device IPs. It sends a multicast discovery request to the CoAP standard multicast address (`224.0.1.187`, port `5683`) and automatically finds all active CoAP servers on the local network.

**What it does:**
- Starts 2–3 CoAP server instances (simulating IoT sensors: temperature, humidity, LED status)
- Each server exposes a `.well-known/core` endpoint listing its resources
- A discovery client sends a multicast `GET /.well-known/core` and collects all responses
- Results are printed showing which devices were found, their IPs, and their resources

**Why it matters:** This is exactly the standard CoAP service discovery mechanism described in RFC 6690 and RFC 7252. Most demo projects skip multicast entirely — this one demonstrates it working end-to-end.

**Expected output:** A table of discovered devices and their resource descriptions (CoRE Link Format).

---

## Module A — CoAP vs HTTP Benchmark

**Goal:** Quantitatively compare CoAP and HTTP for the same IoT-style data exchange, measuring what matters most in constrained networks.

**What it measures:**
- **Packet size** (bytes on the wire) for equivalent GET requests and responses
- **Latency** (round-trip time in milliseconds) averaged over N requests
- **Overhead ratio** (how much extra data HTTP adds vs CoAP)

**What it does:**
- Runs a CoAP server and an HTTP server side-by-side, both returning the same sensor data
- A benchmark client queries both 100 times each and records timing + payload size
- Results are saved to CSV and plotted as bar charts (latency + packet size comparison)

**Expected output:** Two charts and a summary table ready to paste into the report's Results section.

---

## Module C — Network Degradation Resilience (Extra, if time permits)

**Goal:** Test how CoAP behaves under poor network conditions, comparing its two message types:
- **CON (Confirmable):** CoAP retransmits until acknowledged — reliable but slower under loss
- **NON (Non-confirmable):** Fire and forget — faster but lossy

**What it does:**
- Uses Python's `tc` equivalent (or manual packet drop simulation) to introduce artificial packet loss (0%, 5%, 10%, 20%, 30%)
- Sends 50 CON and 50 NON messages at each loss level
- Measures success rate and effective latency for both types

**Expected output:** A line chart showing success rate vs packet loss for CON vs NON — a compelling visual for the Results/Discussion section.

---

## Execution Order

```
1. Run Module B first  →  verify multicast discovery works
2. Run Module A        →  generate benchmark data + charts
3. Run Module C        →  (optional) generate resilience charts
```

---

## Project Structure

```
coap-demo/
│
├── README.md                  ← this file
├── requirements.txt           ← all dependencies
│
├── module_b_discovery/
│   ├── server.py              ← CoAP server simulating an IoT sensor
│   ├── client_discovery.py    ← multicast discovery client
│   └── run_demo.py            ← launches multiple servers + discovery
│
├── module_a_benchmark/
│   ├── coap_server.py         ← CoAP server for benchmarking
│   ├── http_server.py         ← HTTP server for benchmarking
│   ├── benchmark.py           ← runs both tests and records results
│   └── plot_results.py        ← generates charts from CSV
│
├── module_c_degradation/      ← (optional)
│   ├── server.py
│   ├── degradation_test.py
│   └── plot_degradation.py
│
└── results/                   ← auto-generated output folder
    ├── benchmark_results.csv
    ├── latency_chart.png
    ├── packetsize_chart.png
    └── degradation_chart.png  ← (if Module C run)
```

---

## Technologies Used

| Tool | Purpose |
|---|---|
| `aiocoap` | CoAP protocol implementation (server + client) |
| `aiohttp` | HTTP server for benchmarking comparison |
| `scapy` | Low-level packet capture and size measurement |
| `matplotlib` | Chart generation |
| `pandas` | CSV result handling |
| `asyncio` | Async I/O for running servers concurrently |

---

## Notes

- All modules run entirely on localhost / local network (no external hardware needed)
- Tested on Windows with Python 3.10+
- Wireshark can be used alongside any module to visually inspect CoAP UDP packets on port 5683