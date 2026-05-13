# portal/Dockerfile — Cloud Run container for the QuMail portal service.
# Builds liboqs C library from source before installing Python dependencies.
# The desktop app, transport, and UI layers are not included.

FROM python:3.12-slim

# Build tools required for liboqs native C library
RUN apt-get update && apt-get install -y \
    cmake \
    ninja-build \
    gcc \
    g++ \
    git \
    libssl-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Build and install liboqs C library from source — pinned to 0.15.0 to match desktop
RUN git clone --depth 1 --branch 0.15.0 https://github.com/open-quantum-safe/liboqs.git /tmp/liboqs && \
    cmake -S /tmp/liboqs -B /tmp/liboqs/build \
    -DBUILD_SHARED_LIBS=ON \
    -DOQS_BUILD_ONLY_LIB=ON \
    -GNinja && \
    cmake --build /tmp/liboqs/build && \
    cmake --install /tmp/liboqs/build && \
    ldconfig && \
    rm -rf /tmp/liboqs

# Set working directory
WORKDIR /app

# Copy only what the portal service needs
COPY requirements.txt .
COPY core/ ./core/
COPY crypto/ ./crypto/
COPY kme/ ./kme/
COPY portal/ ./portal/

# Install Python dependencies including liboqs-python bindings
RUN pip install --no-cache-dir -r requirements.txt

# Cloud Run listens on 8080
EXPOSE 8080

# Entry point — never calls portal_server.start() or _generate_tls_cert()
CMD ["python", "-m", "portal.cloud_entrypoint"]