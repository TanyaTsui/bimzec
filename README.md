# Circular Construction Logistics in Amsterdam
This repository supports the paper "Logistics for a Circular, Biobased, and Modular Built Environment: Environmental Impacts in Amsterdam" by Tanya Tsui et al. It includes the simulation model, scenario parameters, and relevant data files used to assess the environmental and spatial impacts of construction logistics in circular urban development.

## 🏗️ Overview
As cities aim for more sustainable, circular built environments, logistics systems must adapt. This project explores how different construction strategies—circular, biobased, and modular—affect transportation emissions in the Metropolitan Region of Amsterdam. Using an agent-based model, we simulate logistics flows under six future scenarios, taking into account material reuse, transport modes, and logistics hub configurations.

## 🔍 Research Goals
- Quantify environmental impacts (CO₂, NOₓ, PM₂.₅, PM₁₀) of construction logistics under various circularity, modularity, and material scenarios.
- Assess spatial consequences, including road use and hub siting, of implementing circular logistics systems in dense urban areas.

## 🧠 Methods
- Agent-based modeling (ABM) to simulate material flows from suppliers and demolition sites to construction locations.
- Scenario analysis of 6 logistics configurations varying in:
  - Transport mode (road, water)
  - Truck type (diesel, electric, hybrid)
  - Hub network (none, centralized, decentralized)
  - Material type (conventional, biobased, circular)
  - Construction method (traditional, modular)
- Data sources include OpenStreetMap (via OSMNX), real supplier locations, municipal construction plans, and emission factors from literature and expert consultation.

## 📊 Key Findings
- Circular construction reduces overall emissions but increases local road use due to more frequent, shorter trips from demolition sites.
- Biobased construction can significantly increase emissions if materials are sourced from afar (e.g., Austria).
- Modular construction consistently lowers emissions by consolidating deliveries.
- Water transport lowers CO₂ but increases local air pollutants (NOₓ, PM).
- Decentralized hubs don’t automatically reduce emissions—smarter coordination is needed.
