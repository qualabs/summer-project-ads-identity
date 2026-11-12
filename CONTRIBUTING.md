# Contributing Guide

Thank you for your interest in contributing!
This project explores how talent identity can travel with the video: carrying
HAND IDs (the persistent identifiers for people and their likenesses) from the
ad creative, through the stream, to the ad decision. It is part of
MonteVIDEO Summer Projects 2027.

We welcome contributions of all kinds. You don't need to write code to help:

-   **Code:** proofs of concept, test streams, tooling, code reviews.
-   **Standards knowledge:** SCTE-35, HLS, DASH, SVTA2053, C2PA, ad decisioning.
-   **Operational experience:** where metadata gets lost in real workflows
    (packaging, SSAI, players, ad servers).
-   **Documentation:** implementation guidelines, findings, diagrams.

------------------------------------------------------------------------

## 🧑‍💻 How to Contribute Code

Follow this standard GitHub workflow:

#### 1. Fork the repository

#### 2. Clone your fork

#### 3. Create a feature branch

-   Examples:
    -   `poc/ssai-id-survival`
    -   `feat/scte35-mpu-upid`
    -   `docs/svta2053-mapping`
    -   `fix/daterange-parser`

#### 4. Set up your environment

Each proof of concept lives in its own folder with a README that explains:

-   The question it answers (for example: *does the HAND ID survive SSAI stitching?*)
-   How to set it up and run it
-   What we found

Follow the setup steps in the README of the folder you're working on.

#### 5. Make your changes

-   Write clear, modular code.
-   **Use only synthetic test identities and test HAND IDs.** Never commit real
    people's personal data, images, voices or likenesses.
-   Never commit API keys or credentials.

#### 6. Push your branch

#### 7. Open a Pull Request (PR) with:

- **What** you changed
- **Why** the change is needed (link the PoC question or Issue it relates to)
- **How** to test it
- **Standards references**, if any (e.g. SCTE-35 section, HLS tag, SVTA2053)
- Any **limitations** or **future improvements**

A maintainer will review your PR and provide feedback.

------------------------------------------------------------------------

## 🐛 Reporting Issues and Proposing Ideas

If you find a bug, open an Issue and include:
- Steps to reproduce
- Expected vs actual behavior
- Logs, manifests, SCTE-35 payloads or sample streams if relevant

Questions about the specs, or ideas for new PoCs, are welcome as Issues too.

------------------------------------------------------------------------

## 💬 Join the Community

-   **Discord:** join the video-dev server at https://video-dev.org/discord and
    find us in the *MonteVIDEO Tech Summer Camp* section:
    -   `#project-2027-identity`: this project
    -   `#projects-2027-general`: questions about Summer Projects
    -   `projects-2027-hangout`: voice channel, jump in if you see people there
-   **Weekly sync:** Thursdays, 12:00 Uruguay / 10:00 ET / 16:00 CET.
    Ask in `#project-2027-identity` for the meeting link.

------------------------------------------------------------------------

## 🤝 Code of Conduct

Always communicate with professionalism, kindness, and a spirit of collaboration.
Let's build a positive, respectful, and collaborative community together.

------------------------------------------------------------------------

## 📄 License

This project is licensed under the Apache License 2.0. By contributing, you
agree that your contributions fall under this license.
