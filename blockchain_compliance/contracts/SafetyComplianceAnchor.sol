// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

/**
 * @title SafetyComplianceAnchor
 * @notice Stores Merkle roots of safety event batches for tamper-proof
 *         compliance verification.
 *
 * @dev Only the Merkle root is stored on-chain — not raw event data.
 *      This minimises gas costs while preserving full cryptographic
 *      verifiability through Merkle proofs computed off-chain.
 *
 *      Architecture: Hybrid Anchoring
 *        Local layer  → full event data + local blockchain + Merkle trees
 *        Public layer → Merkle root + timestamp + batch_id (this contract)
 */
contract SafetyComplianceAnchor {

    // --------------------------------------------------------------------- //
    //  Types
    // --------------------------------------------------------------------- //

    struct AnchorRecord {
        bytes32 merkleRoot;
        uint256 timestamp;
        uint256 batchId;
    }

    // --------------------------------------------------------------------- //
    //  State
    // --------------------------------------------------------------------- //

    /// @notice Sequential mapping of batch IDs to their anchor records.
    mapping(uint256 => AnchorRecord) public anchors;

    /// @notice Total number of anchors submitted.
    uint256 public anchorCount;

    /// @notice Address authorised to submit anchors (e.g. the Raspberry Pi wallet).
    address public authorizedSubmitter;

    // --------------------------------------------------------------------- //
    //  Events
    // --------------------------------------------------------------------- //

    /// @notice Emitted every time a new Merkle root is anchored.
    event AnchorSubmitted(
        uint256 indexed batchId,
        bytes32 merkleRoot,
        uint256 timestamp
    );

    // --------------------------------------------------------------------- //
    //  Modifiers
    // --------------------------------------------------------------------- //

    modifier onlyAuthorized() {
        require(msg.sender == authorizedSubmitter, "Unauthorized");
        _;
    }

    // --------------------------------------------------------------------- //
    //  Constructor
    // --------------------------------------------------------------------- //

    /**
     * @param _submitter  Address allowed to call submitAnchor().
     */
    constructor(address _submitter) {
        authorizedSubmitter = _submitter;
    }

    // --------------------------------------------------------------------- //
    //  Write functions
    // --------------------------------------------------------------------- //

    /**
     * @notice Submit a Merkle root for a new batch of safety events.
     * @param _merkleRoot  The 32-byte Merkle root of the event batch.
     */
    function submitAnchor(bytes32 _merkleRoot) external onlyAuthorized {
        uint256 batchId = anchorCount;
        anchors[batchId] = AnchorRecord({
            merkleRoot: _merkleRoot,
            timestamp: block.timestamp,
            batchId: batchId
        });
        anchorCount++;
        emit AnchorSubmitted(batchId, _merkleRoot, block.timestamp);
    }

    // --------------------------------------------------------------------- //
    //  Read functions
    // --------------------------------------------------------------------- //

    /**
     * @notice Retrieve the anchor record for a given batch ID.
     * @param _batchId  The sequential batch identifier.
     * @return merkleRoot  The stored Merkle root.
     * @return timestamp   The block timestamp when the anchor was submitted.
     * @return batchId     The batch identifier (echo).
     */
    function getAnchor(uint256 _batchId)
        external
        view
        returns (bytes32, uint256, uint256)
    {
        AnchorRecord memory record = anchors[_batchId];
        return (record.merkleRoot, record.timestamp, record.batchId);
    }

    /**
     * @notice Verify whether a given Merkle root matches the on-chain record.
     * @param _batchId       The batch to check.
     * @param _expectedRoot  The root the caller expects.
     * @return               True if the roots match.
     */
    function verifyRoot(uint256 _batchId, bytes32 _expectedRoot)
        external
        view
        returns (bool)
    {
        return anchors[_batchId].merkleRoot == _expectedRoot;
    }
}
