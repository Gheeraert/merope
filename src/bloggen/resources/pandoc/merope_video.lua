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

local function refuse(message)
  error('Vidéo Mérope non prise en charge : ' .. message, 0)
end

local function is_valid_youtube_id(id)
  if type(id) ~= 'string' or #id ~= 11 then
    return false
  end
  return id:match('^[%w_%-]+$') ~= nil
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
  local out = {
    pandoc.RawBlock(
      'tei',
      '<p><figure n="' .. video_id .. '"><p><ref type="video-youtube" target="'
        .. target .. '">Vidéo YouTube</ref></p>'
    ),
  }
  if caption ~= nil then
    out[#out + 1] = pandoc.RawBlock('tei', '<figDesc>' .. tei_inline(caption) .. '</figDesc>')
  end
  out[#out + 1] = pandoc.RawBlock('tei', '</figure></p>')
  return out
end
