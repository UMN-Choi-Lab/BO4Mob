FROM python:3.10-slim

# System packages installation
RUN apt-get update && apt-get install -y \
    bash \
    curl \
    vim \
    git \
    cmake \
    g++ \
    build-essential \
    libxerces-c-dev \
    libfox-1.6-dev \
    libgdal-dev \
    libproj-dev \
    libgl2ps-dev \
    libsqlite3-dev \
    python3-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app
COPY . /app

# Install Python libraries from requirements.txt
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

RUN cd /app/sumo/build && \
    cmake -DCMAKE_INSTALL_PREFIX=/opt/sumo-1.12 .. && \
    make -j$(nproc) && \
    make install

# Set environment variables
ENV SUMO_HOME=/opt/sumo-1.12/share/sumo
ENV PATH=$PATH:/opt/sumo-1.12/bin

# Default command
CMD ["bash"]