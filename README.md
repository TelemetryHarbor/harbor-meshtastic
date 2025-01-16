# Harbor Meshtastic Integration  

The **Harbor Meshtastic Integration** script allows you to connect your Meshtastic device to Telemetry Harbor effortlessly. By running this Python code, you can send telemetry data from your Meshtastic device to your Telemetry Harbor account, where it can be visualized using Grafana.  

---  

## Overview  

This integration bridges Meshtastic devices with Telemetry Harbor's powerful data processing and visualization platform. With minimal configuration, you can stream your device data and gain actionable insights through customizable Grafana dashboards.  

---

## Features  

- **Seamless Device Connection**: Easily connect your Meshtastic device via a selected COM port.  
- **Batch Endpoint Support**: Send data directly to Telemetry Harbor's batch ingestion endpoint.  
- **API Key Authentication**: Ensure secure communication using your unique API key.  
- **Real-Time Data Push**: Continuously stream telemetry data for live monitoring and analysis.  
- **Grafana Compatibility**: Visualize your Meshtastic device data with rich Grafana dashboards.  

---

## How to Use  

1. **Prepare Your Meshtastic Device**:  
   - Ensure your Meshtastic device is connected and operational.  
   - Note the COM port associated with the device.  

2. **Set Up the Script**:  
   - Clone this repository:  
     ```bash
     git clone https://github.com/TelemetryHarbor/harbor-meshtastic.git
     cd harbor-meshtastic
     ```  
   - Install required dependencies:  
     ```bash
     pip install -r requirements.txt
     ```  

3. **Run the Script**:  
   - Execute the script and provide the required information:  
     - **Batch Endpoint**: Obtain this from your Telemetry Harbor account.  
     - **API Key**: Your unique key for secure communication.  
     - **COM Port**: The port your Meshtastic device is connected to.  

     ```bash
     python app.py
     ```  

4. **Stream Data**:  
   - The script will push telemetry data from your device to the Telemetry Harbor batch endpoint.  

5. **Visualize in Grafana**:  
   - Log in to your Telemetry Harbor Grafana instance.  
   - Access pre-configured dashboards to view and analyze your Meshtastic data.

## Contribution  

We welcome contributions to enhance the value of these dashboards. If you have suggestions or want to share improvements, feel free to submit your ideas. Collaboration helps us deliver the best tools to our community.  

## About Telemetry Harbor  

Telemetry Harbor is dedicated to simplifying IoT data collection, analysis, and visualization. Our mission is to empower users with tools that make telemetry insights accessible and actionable.  

For more information, visit our website: [Telemetry Harbor](https://telemetryhive.com)  

---  

*Crafted to bring clarity to your data.*  
