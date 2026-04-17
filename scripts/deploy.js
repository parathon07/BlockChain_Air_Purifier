/**
 * Deployment script for SafetyComplianceAnchor.
 *
 * Usage:
 *   npx hardhat node                                        (Terminal 1)
 *   npx hardhat run scripts/deploy.js --network localhost   (Terminal 2)
 *
 * Outputs:
 *   - Deployed contract address printed to console
 *   - deployment.json written to project root for Python to read
 */

const fs = require("fs");
const path = require("path");

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("Deploying with account:", deployer.address);
  console.log(
    "Account balance:",
    (await ethers.provider.getBalance(deployer.address)).toString()
  );

  // Deploy SafetyComplianceAnchor with the deployer as the authorized submitter
  const Contract = await ethers.getContractFactory("SafetyComplianceAnchor");
  const contract = await Contract.deploy(deployer.address);
  await contract.waitForDeployment();

  const contractAddress = await contract.getAddress();
  console.log("SafetyComplianceAnchor deployed to:", contractAddress);
  console.log("Authorized submitter:", deployer.address);

  // Write deployment info for the Python pipeline to consume
  const deploymentInfo = {
    contractAddress: contractAddress,
    authorizedSubmitter: deployer.address,
    network: "localhost",
    deployedAt: new Date().toISOString(),
  };

  const outPath = path.join(__dirname, "..", "deployment.json");
  fs.writeFileSync(outPath, JSON.stringify(deploymentInfo, null, 2));
  console.log("Deployment info saved to:", outPath);
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
