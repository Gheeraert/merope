-- Mérope: Markdown embedded-video div -> native TEI Commons Publishing.
--
-- Pandoc's TEI writer silently drops a fenced div (its class, attributes
-- and wrapper all vanish), so this filter rewrites the reserved Mérope
-- div into raw TEI *before* the writer runs:
--
--   :::: {.merope-video data-provider="youtube" data-video-id="dQw4w9WgXcQ"}
--   Légende facultative.
--   ::::
--
-- becomes
--
--   <figure n="dQw4w9WgXcQ">
--     <p><ref type="video-youtube" target="https://www.youtube.com/watch?v=dQw4w9WgXcQ">Vidéo YouTube</ref></p>
--     <figDesc>Légende facultative.</figDesc>
--   </figure>
--
-- (schema-valid per the bundled TEI Commons Publishing RelaxNG: <figure>
-- accepts <p> via model.common -> model.divPart -> model.pLike, and
-- <figDesc> via model.common; <media>/<ptr> are not available in this
-- profile). Class/attribute names must stay in sync with
-- bloggen/markdown/video_syntax.py.
--
-- Security: the @target/<iframe src> this TEI eventually drives
-- (tei_to_html.xsl) is NEVER built from the user-supplied div attribute
-- strings directly -- only from a video id that passed the strict
-- validation below. An unrecognized provider or a malformed id aborts
-- the whole conversion (refuse()), the same fail-closed behaviour as the
-- encadré filter, rather than silently producing something unsafe or
-- dropping content.

local SUPPORTED_PROVIDERS = { youtube = true }

-- Same bounds and default as bloggen.markdown.video_syntax
-- (DEFAULT_WIDTH/MIN_WIDTH/MAX_WIDTH); validated here independently, from
-- the raw ``data-width`` attribute string, never trusting the Python side
-- already having checked it (a hand-written Markdown file never goes
-- through that module at all).
local DEFAULT_WIDTH = 100
local MIN_WIDTH = 25
local MAX_WIDTH = 100

local function refuse(message)
  error('Vidéo Mérope non prise en charge : ' .. message, 0)
end

local function is_valid_youtube_id(id)
  -- Exactly the same grammar as video_syntax.is_valid_youtube_id's
  -- ``^[A-Za-z0-9_-]{11}$``: explicit ASCII ranges, not Lua's locale-
  -- dependent %w (which is not guaranteed to match only ASCII
  -- alphanumerics), so both validation barriers agree byte-for-byte.
  if type(id) ~= 'string' or #id ~= 11 then
    return false
  end
  return id:match('^[A-Za-z0-9_%-]+$') ~= nil
end

-- Returns the validated integer width, or nil if ``raw`` (the attribute
-- string, possibly absent) is not a bare unsigned integer in range.
local function parse_width(raw)
  if raw == nil then
    return DEFAULT_WIDTH
  end
  if type(raw) ~= 'string' or raw:match('^[0-9]+$') == nil then
    return nil
  end
  local value = tonumber(raw)
  if value == nil or value < MIN_WIDTH or value > MAX_WIDTH then
    return nil
  end
  return value
end

local function tei_inline(inlines)
  -- Render inlines with Pandoc's own TEI writer, then drop the <p> wrapper
  -- it adds around a Plain: <figDesc> holds phrase-level content only
  -- (macro.limitedContent), no <p> child.
  local out = pandoc.write(pandoc.Pandoc({ pandoc.Plain(inlines) }), 'tei')
  out = out:gsub('^%s*<p>', ''):gsub('</p>%s*$', '')
  return out
end

function Div(div)
  if not div.classes:includes('merope-video') then
    return nil
  end

  local provider = div.attributes['data-provider']
  local video_id = div.attributes['data-video-id']

  if provider == nil or not SUPPORTED_PROVIDERS[provider] then
    refuse('fournisseur non pris en charge (' .. tostring(provider) .. ').')
  end
  if not is_valid_youtube_id(video_id) then
    refuse('identifiant vidéo YouTube invalide.')
  end

  local width = parse_width(div.attributes['data-width'])
  if width == nil then
    refuse('largeur invalide (' .. tostring(div.attributes['data-width']) .. ').')
  end

  local blocks = {}
  for _, block in ipairs(div.content) do
    blocks[#blocks + 1] = block
  end
  if #blocks > 1 then
    refuse('une seule légende (un seul paragraphe) est admise.')
  end
  local caption = nil
  if #blocks == 1 then
    local block = blocks[1]
    if block.t ~= 'Para' and block.t ~= 'Plain' then
      refuse('la légende doit être un paragraphe simple.')
    end
    caption = block.content
  end

  -- Built only from the id just validated above, never from the raw
  -- attribute strings or any other user-controlled text.
  local target = 'https://www.youtube.com/watch?v=' .. video_id

  -- Wrapped in its own <p>, exactly like Pandoc's own TEI writer already
  -- wraps a standalone image figure: tei:body requires at least one
  -- "ordinary" content block (model.common, e.g. <p>) in addition to any
  -- model.global content such as a bare <figure> -- a video as the only
  -- body content would otherwise fail Commons Publishing validation. The
  -- existing tei:p template in tei_to_html.xsl already unwraps this exact
  -- shape (a <p> whose only child is a <figure>), so no XSLT change is
  -- needed for this wrapper.
  --
  -- The display width (already validated above, an integer, never a raw
  -- user-controlled string) is carried as @rendition on this same <p>: the
  -- Commons Publishing RelaxNG allows @rendition (a list of anyURI) on
  -- every element via att.global.attributes, and this profile's <figure>
  -- has no free presentation attribute of its own, so this wrapper is the
  -- minimal valid transport. Omitted at the default width so a video
  -- created before this feature -- and any video still at 100 % -- keeps
  -- producing byte-identical TEI.
  local pOpen = '<p>'
  if width ~= DEFAULT_WIDTH then
    pOpen = '<p rendition="urn:merope:video-width:' .. width .. '">'
  end
  local out = {
    pandoc.RawBlock(
      'tei',
      pOpen .. '<figure n="' .. video_id .. '"><p><ref type="video-youtube" target="'
        .. target .. '">Vidéo YouTube</ref></p>'
    ),
  }
  if caption ~= nil then
    out[#out + 1] = pandoc.RawBlock('tei', '<figDesc>' .. tei_inline(caption) .. '</figDesc>')
  end
  out[#out + 1] = pandoc.RawBlock('tei', '</figure></p>')
  return out
end
