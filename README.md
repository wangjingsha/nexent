![Nexent Banner](./assets/NexentBanner.png)

[![English](https://img.shields.io/badge/English-README-blue)](README.md)
[![中文](https://img.shields.io/badge/中文-README-green)](README_CN.md)
[![codecov](https://codecov.io/gh/ModelEngine-Group/nexent/branch/develop/graph/badge.svg?token=00JM5YAD5V)](https://codecov.io/gh/ModelEngine-Group/nexent?branch=develop)

Nexent is an open-source agent platform that turns process-level natural language into complete multimodal agents — no diagrams, no wiring. Built on the MCP tool ecosystem, Nexent provides model integration, data processing, knowledge-base management, and zero-code agent development. Our goal is simple: to bring data, models, and tools together in one smart hub, making daily workflows smarter and more connected.

> One prompt. Endless reach.

### 🌟 Try Nexent Now

- 🌐 Visit our [official website](http://nexent.tech/) to learn more
- 🚀 [Try it now](http://nexent.tech/try) to experience the power of Nexent

https://github.com/user-attachments/assets/0758629c-3477-4cd4-a737-0aab330d53a7

# 🤝 Join Our Community

> *If you want to go fast, go alone; if you want to go far, go together.*

We have released **Nexent v1**, and the platform is now relatively stable. However, there may still be some bugs, and we are continuously improving and adding new features. Stay tuned: we will announce **v2.0** soon!

* **🗺️ Check our [Feature Map](https://github.com/orgs/ModelEngine-Group/projects/6)** to explore current and upcoming features.
* **🔍 Try the current build** and leave ideas or bugs in the [Issues](https://github.com/ModelEngine-Group/nexent/issues) tab.

> *Rome wasn't built in a day.*

If our vision speaks to you, jump in via the **[Contribution Guide](CONTRIBUTING.md)** and shape Nexent with us.

Early contributors won't go unnoticed: from special badges and swag to other tangible rewards, we're committed to thanking the pioneers who help bring Nexent to life.

Most of all, we need visibility. Star ⭐ and watch the repo, share it with friends, and help more developers discover Nexent — your click brings new hands to the project and keeps the momentum growing.

# ⚡ Have a try first

### 1. 📋 Prerequisites  

| Resource | Minimum |
|----------|---------|
| **CPU**  | 2 cores |
| **RAM**  | 6 GiB   |
| **Software** | Docker & Docker Compose installed |

### 2. 🛠️ Quick start with Docker Compose

```bash
git clone https://github.com/ModelEngine-Group/nexent.git
cd nexent/docker
cp .env.example .env # fill only nessasary configs
bash deploy.sh
```

When the containers are running, open **http://localhost:3000** in your browser and follow the setup wizard.

### 3. 🤖 Model Configuration & Provider Recommendations

We recommend the following model providers:

| Model Type | Provider | Notes |
|------------|----------|-------|
| LLM & VLLM | [Silicon Flow](https://siliconflow.cn/) | Free tier available |
| LLM & VLLM | [Alibaba Bailian](https://bailian.console.aliyun.com/) | Free tier available |
| Embedding | [Jina](https://jina.ai/) | Free tier available |
| TTS & STT | [Volcengine Voice](https://www.volcengine.com/product/voice-tech) | Free for personal use |
| Search | [EXA](https://exa.ai/) | Free tier available |

You'll need to input the following information in the model configuration page:
- Base URL
- API Key
- Model Name

The following configurations need to be added to your `.env` file (we'll make these configurable through the frontend soon):
- TTS and STT related configurations
- EXA search API Key

> ℹ️ Due to core features development, currently, we only support Jina Embedding model. Support for other models will be added in future releases. For Jina API key setup, please refer to our [FAQ](FAQ.md).

### 4. ❓ Need help?

- Browse the [FAQ](FAQ.md) for common install issues.  
- Drop questions in our [Discord community](https://discord.gg/tb5H3S3wyv).  
- File bugs or feature ideas in [GitHub Issues](https://github.com/ModelEngine-Group/nexent/issues).

### 5. 🔧 Hack on Nexent

Want to build from source or add new features? Check the [Contribution Guide](CONTRIBUTING.md) for step-by-step instructions.

### 6. 🛠️ Build from Source

Prefer to run Nexent from source code? Follow our [Developer Guide](DEVELOPPER_NOTE.md) for detailed setup instructions and customization options.

## ✨ Key Features

`1` **Smart agent prompt generation**  
   Turn plain language into runnable prompts. Nexent automatically chooses the right tools and plans the best action path for every request.

   ![Feature 1](./assets/Feature1.png)

`2` **Scalable data process engine**  
   Process 20+ data formats with fast OCR and table structure extraction, scaling smoothly from a single process to large-batch pipelines.

   ![Feature 2](./assets/Feature2.png)

`3` **Personal-grade knowledge base**  
   Import files in real time, auto-summarise them, and let agents access both personal and global knowledge instantly, also knowing what it can get from each knowledge base.

   ![Feature 3](./assets/Feature3.png)

`4` **Internet knowledge search**  
   Connect to 5+ web search providers so agents can mix fresh internet facts with your private data.

   ![Feature 4](./assets/Feature4.png)

`5` **Knowledge-level traceability**  
   Serve answers with precise citations from web and knowledge-base sources, making every fact verifiable.

   ![Feature 5](./assets/Feature5.png)

`6` **Multimodal understanding & dialogue**  
   Speak, type, files, or show images. Nexent understands voice, text, and pictures, and can even generate new images on demand.

   ![Feature 6](./assets/Feature6.png)

`7` **MCP tool ecosystem**  
   Drop in or build Python plug-ins that follow the MCP spec; swap models, tools, and chains without touching core code.

   ![Feature 7](./assets/Feature7.png)

# 🐛 Known Issues

1📝 **Code Output May Be Misinterpreted as Executable**  
   In Nexent conversations, if the model outputs code-like text, it may sometimes be misinterpreted as something that should be executed. We will fix this as soon as possible.

# 👥 External Developer Contribution Guide

We welcome all kinds of contributions! Whether you're fixing bugs, adding features, or improving documentation, your help makes Nexent better for everyone. 

If you are an external developer and want to contribute to this project, please follow these steps:

1. **Fork the repository**
   - Click the "Fork" button at the top right of the repository page to create your own copy.
2. **Clone your fork**
   - Use `git clone https://github.com/your-username/your-forked-repo.git` to clone your fork to your local machine.
3. **Commit and push your changes**
   - Make your changes, then use `git add .`, `git commit -m "Your message"`, and `git push origin` to push to your fork.
4. **Open a Pull Request**
   - Go to your forked repository on GitHub, click the "Contribute" button, and then select "Open Pull Request" to propose merging your changes into the main repository.

Please make sure your PR follows the project's contribution guidelines and passes all required checks.

- 📖 Read our [Contribution Guide](CONTRIBUTING.md) to get started
- 🐛 Report bugs or suggest features in [GitHub Issues](https://github.com/ModelEngine-Group/nexent/issues)
- 💬 Join our [Discord community](https://discord.gg/tb5H3S3wyv) to discuss ideas

# 💬 Community & contact

Join our [Discord community](https://discord.gg/tb5H3S3wyv) to chat with other developers and get help!

# 📄 License

Nexent is licensed under the [MIT](LICENSE) with additional conditions. Please read the [LICENSE](LICENSE) file for details.

