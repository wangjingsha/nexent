### 🏗️ Build and Push Images

```bash
# 🛠️ Create and use a new builder instance that supports multi-architecture builds
docker buildx create --name nexent_builder --use

# 🚀 build application for multiple architectures
docker buildx build --progress=plain --platform linux/amd64,linux/arm64 -t nexent/nexent -f make/main/Dockerfile . --push
docker buildx build --progress=plain --platform linux/amd64,linux/arm64 -t ccr.ccs.tencentyun.com/nexent-hub/nexent -f make/web/Dockerfile . --push

# 📊 build data_process for multiple architectures
docker buildx build --progress=plain --platform linux/amd64,linux/arm64 -t nexent/nexent-data-process -f make/data_process/Dockerfile . --push
docker buildx build --progress=plain --platform linux/amd64,linux/arm64 -t ccr.ccs.tencentyun.com/nexent-hub/nexent-data-process -f make/web/Dockerfile . --push

# 🌐 build web frontend for multiple architectures
docker buildx build --progress=plain --platform linux/amd64,linux/arm64 -t nexent/nexent-web -f make/web/Dockerfile . --push
docker buildx build --progress=plain --platform linux/amd64,linux/arm64 -t ccr.ccs.tencentyun.com/nexent-hub/nexent-web -f make/web/Dockerfile . --push

# 📚 build documentation for multiple architectures
docker buildx build --progress=plain --platform linux/amd64,linux/arm64 -t nexent/nexent-docs -f make/docs/Dockerfile . --push
docker buildx build --progress=plain --platform linux/amd64,linux/arm64 -t ccr.ccs.tencentyun.com/nexent-hub/nexent-docs -f make/docs/Dockerfile . --push
```

### 💻 Local Development Build

```bash
# 🚀 Build application image (current architecture only)
docker build --progress=plain -t nexent/nexent -f make/main/Dockerfile .

# 📊 Build data process image (current architecture only)
docker build --progress=plain -t nexent/nexent-data-process -f make/data_process/Dockerfile .

# 🌐 Build web frontend image (current architecture only)
docker build --progress=plain -t nexent/nexent-web -f make/web/Dockerfile .

# 📚 Build documentation image (current architecture only)
docker build --progress=plain -t nexent/nexent-docs -f make/docs/Dockerfile .
```

### 🧹 Clean up Docker resources

```bash
# 🧼 Clean up Docker build cache and unused resources
docker builder prune -f && docker system prune -f
```

### 🔧 Image Descriptions

#### Main Application Image (nexent/nexent)
- Contains backend API service
- Built from `make/main/Dockerfile`
- Provides core agent services

#### Data Processing Image (nexent/nexent-data-process)
- Contains data processing service
- Built from `make/data_process/Dockerfile`
- Handles document parsing and vectorization

#### Web Frontend Image (nexent/nexent-web)
- Contains Next.js frontend application
- Built from `make/web/Dockerfile`
- Provides user interface

#### Documentation Image (nexent/nexent-docs)
- Contains Vitepress documentation site
- Built from `make/docs/Dockerfile`
- Provides project documentation and API reference

### 🏷️ Tagging Strategy

Each image is pushed to two repositories:
- `nexent/*` - Main public image repository
- `ccr.ccs.tencentyun.com/nexent-hub/*` - Tencent Cloud image repository (China region acceleration)

All images include:
- `nexent/nexent` - Main application backend service
- `nexent/nexent-data-process` - Data processing service
- `nexent/nexent-web` - Next.js frontend application
- `nexent/nexent-docs` - Vitepress documentation site

## 📚 Documentation Image Standalone Deployment

The documentation image can be built and run independently to serve nexent.tech/doc:

### Build Documentation Image

```bash
docker build -t nexent/nexent-docs -f make/docs/Dockerfile .
```

### Run Documentation Container

```bash
docker run -d --name nexent-docs -p 4173:4173 nexent/nexent-docs
```

### Check Container Status

```bash
docker ps
```

### View Container Logs

```bash
docker logs nexent-docs
```

### Stop and Remove Container

```bash
docker stop nexent-docs
```

```bash
docker rm nexent-docs
```

Notes:
- 🔧 Use `--platform linux/amd64,linux/arm64` to specify target architectures
- 📤 The `--push` flag automatically pushes the built images to Docker Hub
- 🔑 Make sure you are logged in to Docker Hub (`docker login`)
- ⚠️ If you encounter build errors, ensure Docker's buildx feature is enabled
- 🧹 Cleanup commands explanation:
  - `docker builder prune -f`: Cleans build cache
  - `docker system prune -f`: Cleans unused data (including dangling images, networks, etc.)
  - The `-f` flag forces execution without confirmation
- 🔧 The `--load` flag loads the built image into the local Docker images list
- ⚠️ `--load` can only be used with single architecture builds
- 📝 Use `docker images` to verify the images are loaded locally
- 📊 Use `--progress=plain` to see detailed build and push progress
- 📈 Use `--build-arg MIRROR=...` to set up a pip mirror to accelerate your build-up progress