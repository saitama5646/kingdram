
CREATE TABLE IF NOT EXISTS alliance_invitations (
    id BIGSERIAL PRIMARY KEY,
    alliance_id BIGINT NOT NULL
        REFERENCES alliances(id) ON DELETE CASCADE,
    player_id BIGINT NOT NULL
        REFERENCES players(id) ON DELETE CASCADE,
    invited_by BIGINT NOT NULL
        REFERENCES players(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (
            status IN (
                'pending',
                'accepted',
                'rejected',
                'cancelled'
            )
        ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_at TIMESTAMPTZ,
    CHECK (player_id <> invited_by)
);

CREATE UNIQUE INDEX IF NOT EXISTS
idx_kingdram_alliance_pending_invitation
ON alliance_invitations(alliance_id, player_id)
WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS
idx_kingdram_alliance_player_invitations
ON alliance_invitations(player_id, status);

INSERT INTO alliance_members (
    alliance_id,
    player_id
)
SELECT
    a.id,
    a.leader_id
FROM alliances a
WHERE NOT EXISTS (
    SELECT 1
    FROM alliance_members am
    WHERE am.alliance_id = a.id
      AND am.player_id = a.leader_id
)
ON CONFLICT DO NOTHING;
